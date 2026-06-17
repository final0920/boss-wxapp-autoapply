"""BOSS直聘 微信小程序驱动 —— CDP/Frida 注入（渲染层 DOM 读 + Input 真实触摸）。

与 ms 的 BossDriver 同一套契约（runner/dispatcher/inbox_watcher 依赖）。M0 实测(plan §2.5)：
- 读：CDP 连渲染层根帧；职位内容在同源子 iframe，`iframe.contentDocument` 直读（精确，零 OCR）。
  列表卡 = wx-view.job-card--job（在 wx-view.job-list），innerText 规整分行可解析。
- 写：cdp.touch(x,y)=Input.dispatchTouchEvent 于根视口坐标触发 bindtap（鼠标无效）。

坐标 cx/cy 为**根视口像素**（= iframe 偏移 + 元素中心），供 cdp.touch 直接用。
dump() 返回当前详情页文本快照（read_chat_button_label/scrape_detail_fields 解析它）。
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from app.cdp import get_cdp
from app.pipeline.collector import RawJob

logger = logging.getLogger(__name__)

_SAL = re.compile(r"\d+\s*[-~]\s*\d+\s*[Kk]")
_EXP = re.compile(r"\d+-?\d*年(以上|以内)?|经验不限|应届|在校")
_DEGREE = ("学历不限", "初中及以下", "中专", "中技", "高中", "大专", "本科", "硕士", "博士")
# 仅保留滑块/拼图类验证页特有文案；剔除"请完成"(如"请完成在线简历")、"人机" 等
# 正常 UI 也会出现的泛词，避免误判。检测口径见 detect_verify（只扫可见在屏帧）。
_VERIFY_KW = ("拖动", "滑块", "向右滑", "拼图", "安全验证", "点击验证", "验证码")


@dataclass
class JobCard:
    raw: RawJob
    cx: int
    cy: int


# ---------------------------------------------------------------------------
# JS（在根帧执行，经同源 iframe.contentDocument 访问页面内容）
# ---------------------------------------------------------------------------
# 找含薪资卡片的 iframe，抽取每张卡的 innerText + 根视口点击坐标
_JS_SCRAPE = r"""(function(){
  var ifr=document.querySelectorAll('iframe'),d=null,fr=null;
  for(var i=0;i<ifr.length;i++){try{var e=ifr[i];var cs=getComputedStyle(e);
    if(cs.visibility!=='visible'||cs.display==='none')continue;
    var rr=e.getBoundingClientRect();if(rr.left<-60||rr.left>60||rr.width<200||rr.height<300)continue;
    var dd=e.contentDocument;if(dd&&/\d+\s*[-~]\s*\d+\s*[Kk]/.test(dd.body?dd.body.innerText:'')){d=dd;fr=rr;break;}}catch(e){}}
  if(!d)return JSON.stringify({err:'no-list',cards:[]});
  var SAL=/\d+\s*[-~]\s*\d+\s*[Kk]/,vt=fr.top,vb=fr.top+fr.height,vl=fr.left,vrt=fr.left+fr.width;
  var sal=Array.prototype.filter.call(d.querySelectorAll('*'),function(e){return SAL.test(e.textContent||'')&&Array.prototype.every.call(e.children,function(c){return !SAL.test(c.textContent||'');});});
  var cards=[],seen=[];
  sal.forEach(function(e){
    var c=e,card=null;while(c){var L=(c.innerText||'').length;if(L>=40&&L<=360){card=c;break;}c=c.parentElement;}
    if(!card||seen.indexOf(card)>=0)return;seen.push(card);
    var r=card.getBoundingClientRect();if(r.height<40||r.width<60)return;
    var x=fr.left+r.left+r.width/2,y=fr.top+r.top+Math.min(30,r.height/2);
    if(x<vl+4||x>vrt-4||y<vt+44||y>vb-4)return;   // 仅在屏可点卡
    cards.push({text:card.innerText,x:Math.round(x),y:Math.round(y)});
  });
  return JSON.stringify({n:cards.length,cards:cards});
})()"""

# 找详情 iframe，返回其文本
_JS_DETAIL_TEXT = r"""(function(){
  var ifr=document.querySelectorAll('iframe');
  for(var i=0;i<ifr.length;i++){try{var d=ifr[i].contentDocument;if(d){var t=(d.body?d.body.innerText:'');if(/立即沟通|继续沟通|职位详情|职位描述/.test(t))return t;}}catch(e){}}
  return '';
})()"""

# 在详情 iframe 定位「立即沟通/继续沟通」按钮的根视口坐标
_JS_LOCATE_CHAT = r"""(function(){
  var ifr=document.querySelectorAll('iframe');
  for(var i=0;i<ifr.length;i++){try{var d=ifr[i].contentDocument;if(!d)continue;var t=(d.body?d.body.innerText:'');if(!/立即沟通|继续沟通/.test(t))continue;
    var fr=ifr[i].getBoundingClientRect();
    var els=d.querySelectorAll('*'),btn=null;
    for(var j=0;j<els.length;j++){var x=els[j].textContent||'';if((x==='立即沟通'||x==='继续沟通')&&els[j].children.length<=1){btn=els[j];break;}}
    if(!btn){for(var k=0;k<els.length;k++){var y=els[k].textContent||'';if(/^(立即沟通|继续沟通)$/.test(y.trim())){btn=els[k];break;}}}
    if(btn){var r=btn.getBoundingClientRect();return JSON.stringify({found:true,label:btn.textContent.trim(),x:Math.round(fr.left+r.left+r.width/2),y:Math.round(fr.top+r.top+r.height/2)});}
  }catch(e){}}
  return JSON.stringify({found:false});
})()"""

# 前台页类型：只看 **visibility:visible** 的在屏 iframe（后台/弹出页被弹出后 visibility:hidden，
# 但仍留在 left≈0、内容残留——这是不连投/卡死/误判 chat 的根因）。返回单一页型。
_JS_FG_PAGE = r"""(function(){var ifr=document.querySelectorAll('iframe'),SAL=/\d+\s*[-~]\s*\d+\s*[Kk]/;
  for(var i=0;i<ifr.length;i++){var e=ifr[i];var cs=getComputedStyle(e);
    if(cs.visibility!=='visible'||cs.display==='none')continue;
    var r=e.getBoundingClientRect();if(r.width<200||r.height<200||r.left<-60||r.left>60)continue;
    var t='';try{var d=e.contentDocument;if(d&&d.body)t=d.body.innerText||'';}catch(x){continue;}
    if(!t)continue;
    if(/常用语|由你发起/.test(t))return 'chat';
    if(/立即沟通|继续沟通/.test(t)||(/职位详情/.test(t)&&/该公司其他岗位|BOSS安全提示/.test(t)))return 'detail';
    if(/新招呼/.test(t)&&/仅沟通/.test(t))return 'msglist';
    if(/新职位/.test(t)&&SAL.test(t))return 'feed';
    if(SAL.test(t))return 'list';
  }
  return 'unknown';})()"""


def _find_text_coord(keywords: list[str]) -> str:
    """生成 JS：在所有 iframe + 根帧找含任一关键词的可点元素，返回根视口坐标。"""
    kw = json.dumps(keywords, ensure_ascii=False)
    return r"""(function(){
  var KW=%s;
  function hit(t){t=(t||'').trim();for(var i=0;i<KW.length;i++){if(t===KW[i])return true;}return false;}
  function scan(doc,fr){var els=doc.querySelectorAll('*');for(var j=0;j<els.length;j++){if(hit(els[j].textContent)&&els[j].children.length<=1){var r=els[j].getBoundingClientRect();if(r.width>0&&r.height>0)return{x:Math.round(fr.left+r.left+r.width/2),y:Math.round(fr.top+r.top+r.height/2),label:els[j].textContent.trim()};}}return null;}
  var rootfr={left:0,top:0};var rr=scan(document,rootfr);if(rr)return JSON.stringify(Object.assign({found:true},rr));
  var ifr=document.querySelectorAll('iframe');
  for(var i=0;i<ifr.length;i++){try{var d=ifr[i].contentDocument;if(!d)continue;var r=scan(d,ifr[i].getBoundingClientRect());if(r)return JSON.stringify(Object.assign({found:true},r));}catch(e){}}
  return JSON.stringify({found:false});
})()""" % kw


def _parse_card(text: str) -> RawJob:
    """解析卡片 innerText（标题\\n薪资\\n公司 规模 融资\\n经验+学历+标签\\nHR·职务\\n地点）。"""
    lines = [ln.strip() for ln in text.replace(" ", " ").split("\n") if ln.strip()]
    sal_i = next((i for i, ln in enumerate(lines) if _SAL.search(ln)), -1)
    salary = lines[sal_i] if sal_i >= 0 else ""
    title = lines[sal_i - 1] if sal_i > 0 else (lines[0] if lines else "")
    company = scale = finance = experience = degree = hr_name = hr_title = area = ""
    rest = lines[sal_i + 1:] if sal_i >= 0 else lines
    if rest:
        parts = re.split(r"\s{1,}", rest[0])
        company = parts[0] if parts else ""
        for p in parts[1:]:
            if re.search(r"\d+\s*-\s*\d+人|人$|\d+人", p):
                scale = p
            elif p:
                finance = finance or p
    for ln in rest[1:]:
        if "·" in ln and not hr_name:
            seg = ln.split("·", 1)
            hr_name = seg[0].strip()
            hr_title = seg[1].strip() if len(seg) > 1 else ""
        m = _EXP.search(ln)
        if m and not experience:
            experience = m.group(0)
        for dg in _DEGREE:
            if dg in ln and not degree:
                degree = dg
    if rest and "·" not in rest[-1] and not _SAL.search(rest[-1]):
        area = rest[-1]
    return RawJob(title=title, company=company, salary=salary, area=area, degree=degree,
                  experience=experience, company_scale=scale, finance_stage=finance,
                  hr_name=hr_name, hr_title=hr_title)


class BossWxappDriver:
    def __init__(self, serial: str = "") -> None:
        self.serial = serial
        self._cdp = None

    @property
    def cdp(self):
        if self._cdp is None:
            self._cdp = get_cdp()
        self._cdp.ensure_connected()
        return self._cdp

    def _eval(self, expr: str):
        return self.cdp.evaluate(expr)

    # ------------------------------------------------------------------
    def prepare_device(self) -> None:
        """连 CDP（WMPFDebugger 代理）。"""
        c = get_cdp()
        c.connect()
        self._cdp = c
        time.sleep(0.3)

    def dump(self) -> Optional[str]:
        """详情页文本快照（供 read_chat_button_label/scrape_detail_fields）。"""
        try:
            return self._eval(_JS_DETAIL_TEXT)
        except Exception as e:  # noqa: BLE001
            logger.warning("dump 失败: %s", e)
            return None

    def detect_verify(self) -> bool:
        """风控/验证页检测。

        只扫 **visibility:visible 且在屏** 的 iframe（与页面判定 _vis_has 同口径）——
        旧实现扫了根文档 + 所有 iframe（含后台残留帧），叠加泛关键词导致界面正常时
        仍常驻误判。命中即记录具体关键词，便于复盘是哪个词/页触发。
        """
        kw = json.dumps(_VERIFY_KW, ensure_ascii=False)
        js = (r"""(function(){var KW=%s;var f=document.querySelectorAll('iframe');
          for(var i=0;i<f.length;i++){var e=f[i];var cs=getComputedStyle(e);
            if(cs.visibility!=='visible'||cs.display==='none')continue;
            var r=e.getBoundingClientRect();if(r.width<200||r.height<300||r.left<-60||r.left>60)continue;
            try{var d=e.contentDocument;var t=d&&d.body?d.body.innerText:'';
              for(var j=0;j<KW.length;j++){if(t.indexOf(KW[j])>=0)return KW[j];}}catch(x){}}
          return '';})()""" % kw)
        try:
            hit = self._eval(js)
            if hit:
                logger.warning("detect_verify 命中风控关键词: %s", hit)
            return bool(hit)
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # 列表采集（CDP 全量）
    # ------------------------------------------------------------------
    def scrape_page(self) -> list[JobCard]:
        try:
            data = json.loads(self._eval(_JS_SCRAPE))
        except Exception as e:  # noqa: BLE001
            logger.warning("scrape_page 失败: %s", e)
            return []
        cards: list[JobCard] = []
        for c in data.get("cards", []):
            raw = _parse_card(c.get("text", ""))
            if not raw.title or not raw.company:
                continue
            cards.append(JobCard(raw=raw, cx=int(c["x"]), cy=int(c["y"])))
        return cards

    def scroll_list(self) -> None:
        """上滑可见 feed 视口加载更多（真实滑动手势；scrollTop 对小程序 scroll-view 无效）。"""
        try:
            vp = self._eval(r"""(function(){var f=document.querySelectorAll('iframe');for(var i=0;i<f.length;i++){
              var e=f[i];var cs=getComputedStyle(e);if(cs.visibility!=='visible'||cs.display==='none')continue;
              var r=e.getBoundingClientRect();if(r.width<200||r.height<300||r.left<-60||r.left>60)continue;
              var d=e.contentDocument;if(d&&/\d+\s*[-~]\s*\d+\s*[Kk]/.test(d.body?d.body.innerText:''))
                return JSON.stringify({cx:Math.round(r.left+r.width/2),top:Math.round(r.top),bot:Math.round(r.top+r.height)});}return '';})()""")
            if vp:
                v = json.loads(vp)
                cx = int(v["cx"])
                self.cdp.swipe(cx, int(v["bot"]) - 90, cx, int(v["top"]) + 120)
        except Exception as e:  # noqa: BLE001
            logger.warning("scroll_list 失败: %s", e)
        time.sleep(1.0)

    def refresh_feed(self) -> None:
        """回顶 + 下拉刷新新职位 feed，捕获新推送的职位（投尽后等新岗用）。"""
        self._touch_text(["回顶部"], wait=1.0)
        try:
            vp = self._eval(r"""(function(){var f=document.querySelectorAll('iframe');for(var i=0;i<f.length;i++){
              var e=f[i];var cs=getComputedStyle(e);if(cs.visibility!=='visible'||cs.display==='none')continue;
              var r=e.getBoundingClientRect();if(r.width<200||r.height<300||r.left<-60||r.left>60)continue;
              var d=e.contentDocument;if(d&&/\d+\s*[-~]\s*\d+\s*[Kk]/.test(d.body?d.body.innerText:''))
                return JSON.stringify({cx:Math.round(r.left+r.width/2),top:Math.round(r.top)});}return '';})()""")
            if vp:
                v = json.loads(vp)
                cx, top = int(v["cx"]), int(v["top"])
                self.cdp.swipe(cx, top + 130, cx, top + 520)  # 下拉刷新
        except Exception as e:  # noqa: BLE001
            logger.warning("refresh_feed 失败: %s", e)
        time.sleep(1.8)

    def _tap_until(self, cx: int, cy: int, target_kw: str = "",
                   retries: int = 3, wait: float = 1.2) -> bool:
        """触摸根视口坐标，DOM 校验是否到达目标页。"""
        for _ in range(retries):
            self.cdp.touch(cx, cy)
            time.sleep(wait)
            if not target_kw:
                return True
            txt = self.dump() or ""
            if "详情" in target_kw and ("职位详情" in txt or "立即沟通" in txt or "继续沟通" in txt):
                return True
        return False

    # ------------------------------------------------------------------
    # 详情读取 / 投递
    # ------------------------------------------------------------------
    def read_chat_button_label(self, detail: str) -> str:
        t = detail or ""
        if "继续沟通" in t:
            return "继续沟通"
        if "立即沟通" in t:
            return "立即沟通"
        return ""

    def scrape_detail_fields(self, detail: str) -> dict[str, str]:
        t = detail or ""
        lines = [ln.strip() for ln in t.replace(" ", " ").split("\n") if ln.strip()]
        fields = {"location": "", "experience": "", "degree": "", "hr_name": "",
                  "hr_title": "", "hr_active": "", "jd": ""}
        for ln in lines:
            if not fields["location"] and "·" in ln and re.search(
                    r"北京|上海|广州|深圳|杭州|武汉|成都|南京|西安|苏州|长沙|郑州|合肥|区", ln) and len(ln) < 30:
                fields["location"] = ln
            if not fields["experience"]:
                m = _EXP.search(ln)
                if m and len(ln) < 14:
                    fields["experience"] = m.group(0)
            if not fields["degree"]:
                for dg in _DEGREE:
                    if ln == dg or (dg in ln and len(ln) < 12):
                        fields["degree"] = dg
                        break
            if not fields["hr_active"] and ("活跃" in ln or "回复" in ln or "在线" in ln):
                fields["hr_active"] = ln
            if not fields["hr_title"] and "·" in ln and ("hr" in ln.lower() or "招聘" in ln or "经理" in ln
                                                          or "总监" in ln or "总裁" in ln or "人事" in ln):
                fields["hr_title"] = ln
                fields["hr_name"] = ln.split("·")[0].strip()
        # JD：详情正文（取「职位详情/职位描述」后较长段）
        jd_start = next((i for i, ln in enumerate(lines) if "职位详情" in ln or "职位描述" in ln), -1)
        jd_lines = lines[jd_start + 1:] if jd_start >= 0 else lines
        fields["jd"] = " ".join(x for x in jd_lines if len(x) >= 4)[:1500]
        return fields

    def tap_chat_and_capture(self) -> tuple[bool, str, str]:
        """CDP 定位「立即沟通」→ touch 一次（BOSS 即时发默认招呼并进会话，异步 2-3s）→
        轮询进会话（**不重复点**，避免落到会话页元素误触）→ 抓招呼语。"""
        try:
            loc = json.loads(self._eval(_JS_LOCATE_CHAT))
        except Exception as e:  # noqa: BLE001
            return False, "", f"定位沟通按钮失败: {e}"
        if not loc.get("found"):
            return False, "", "未找到沟通按钮"
        self.cdp.touch(int(loc["x"]), int(loc["y"]))
        for _ in range(12):
            time.sleep(1.0)
            if self._on_chat():
                return True, self._grab_greeting(), ""
        # 仍未进会话，重试一次点击（防首次未命中）
        self.cdp.touch(int(loc["x"]), int(loc["y"]))
        for _ in range(8):
            time.sleep(1.0)
            if self._on_chat():
                return True, self._grab_greeting(), ""
        return False, "", "未跳转聊天页（超时）"

    def _vis_has(self, pat: str) -> bool:
        """前台(visibility:visible 在屏)iframe 的 innerText 是否匹配正则 pat。
        聊天页一个 iframe 装所有子tab内容、已弹出页 visibility:hidden 但内容残留——
        故页面判定必须只看可见帧（这是不连投/卡死/误判的根因）。"""
        js = (r"""(function(){var f=document.querySelectorAll('iframe');for(var i=0;i<f.length;i++){
          var e=f[i];var cs=getComputedStyle(e);if(cs.visibility!=='visible'||cs.display==='none')continue;
          var r=e.getBoundingClientRect();if(r.width<200||r.height<300||r.left<-60||r.left>60)continue;
          try{var d=e.contentDocument;if(d&&d.body&&(%s).test(d.body.innerText||''))return true;}catch(x){}}return false;})()""" % pat)
        try:
            return bool(self._eval(js))
        except Exception:  # noqa: BLE001
            return False

    def _on_chat(self) -> bool:
        """前台是会话页：用「常用语」(会话底部快捷语按钮，消息列表/feed 都没有)。
        不用「送达/由你发起」——消息列表的会话预览里就有，会误判。"""
        return self._vis_has(r"/常用语/")

    def _on_detail(self) -> bool:
        """前台是职位详情页（立即沟通/继续沟通 按钮）。"""
        return self._vis_has(r"/立即沟通|继续沟通/")

    def _grab_greeting(self) -> str:
        """我方招呼语 = 会话页「送达」上一条消息行（"由你发起"之后、HR 回复之前）。
        不能取最长行——HR 自动回复常比招呼语长，会被误取（实测 bug）。"""
        try:
            return self._eval(
                r"""(function(){var f=document.querySelectorAll('iframe');for(var i=0;i<f.length;i++){
                  var e=f[i];var cs=getComputedStyle(e);if(cs.visibility!=='visible'||cs.display==='none')continue;
                  var rr=e.getBoundingClientRect();if(rr.width<200||rr.height<300||rr.left<-60||rr.left>60)continue;
                  try{var d=e.contentDocument;if(!d)continue;var t=d.body?d.body.innerText:'';
                  if(!/常用语/.test(t))continue;
                  var ls=t.split('\n').map(function(s){return s.trim();}).filter(Boolean);
                  function skip(s){return /^\d{1,2}:\d{2}$/.test(s)||/^\d+月\d+日/.test(s)||/由你发起/.test(s)||/^(已读|未读|送达|常用语|新信息|换微信|换电话|发简历|更多)$/.test(s);}
                  var bi=-1;for(var m=0;m<ls.length;m++){if(ls[m].indexOf('由你发起')>=0){bi=m;break;}}
                  if(bi>=0){for(var n=bi+1;n<ls.length;n++){if(skip(ls[n]))continue;if(ls[n].length>=4)return ls[n];}}
                  var di=-1;for(var k=0;k<ls.length;k++){if(ls[k].indexOf('送达')>=0){di=k;break;}}
                  if(di>0){for(var j=di-1;j>=0;j--){if(skip(ls[j]))continue;if(ls[j].length>=4)return ls[j];}}
                  return '';}catch(e){}}return '';})()""") or ""
        except Exception:  # noqa: BLE001
            return ""

    # ------------------------------------------------------------------
    # 页面判定 / 导航
    # ------------------------------------------------------------------
    def _on_list(self) -> bool:
        return not self._on_chat() and not self._on_detail() and len(self.scrape_page()) >= 1

    def fg_page(self) -> str:
        """前台页型分类（只看可见在屏帧）：chat|detail|msglist|feed|list|unknown。"""
        try:
            return self._eval(_JS_FG_PAGE) or "unknown"
        except Exception:  # noqa: BLE001
            return "unknown"

    def ensure_on_list(self, max_try: int = 5) -> bool:
        """回到「职位」推荐列表锚点。

        以页型分类(fg_page)为准、而非 scrape 卡数——曾因列表已在屏但本帧 scrape
        暂为 0 就判定"未回到锚点"，导致明明停在列表却空转重试。失败时打印当前
        页型+卡数，便于定位到底卡在哪一页。
        """
        for _ in range(max_try):
            pg = self.fg_page()
            if pg == "list" or self._on_list():
                return True
            if pg in ("chat", "detail", "msglist"):
                # 先退出会话/详情/消息列表，下一轮再切 tab
                self._press_back()
                time.sleep(1.0)
                continue
            # feed / unknown：切到底部「职位」tab
            self.goto_list()
            if self.fg_page() == "list" or self._on_list():
                return True
            time.sleep(0.8)
        logger.warning("ensure_on_list 未回到列表：页型=%s scrape=%d",
                       self.fg_page(), len(self.scrape_page()))
        return False

    def goto_list(self) -> bool:
        """导航到底部「职位」tab（职位推荐列表）。"""
        self._touch_text(["职位"], wait=1.8)
        for _ in range(4):
            if self._on_list():
                return True
            time.sleep(0.6)
        return self._on_list()

    def _touch_text(self, keywords: list[str], wait: float = 1.2) -> bool:
        try:
            loc = json.loads(self._eval(_find_text_coord(keywords)))
        except Exception:  # noqa: BLE001
            return False
        if loc.get("found"):
            self.cdp.touch(int(loc["x"]), int(loc["y"]))
            time.sleep(wait)
            return True
        return False

    def _press_back(self) -> bool:
        """点小程序自定义导航栏「返回」(u-back-wrap，左上角)逐级退栈；失效兜底固定坐标。"""
        js = r"""(function(){var ifr=document.querySelectorAll('iframe'),best=null;
          for(var i=0;i<ifr.length;i++){try{var d=ifr[i].contentDocument;if(!d)continue;
            var fr=ifr[i].getBoundingClientRect();
            var els=d.querySelectorAll('[class*=u-back],[class*=back-wrap],[class*=nav-back]');
            for(var j=0;j<els.length;j++){var e=els[j];var r=e.getBoundingClientRect();
              var ax=fr.left+r.left+r.width/2,ay=fr.top+r.top+r.height/2;
              if(r.width>0&&r.width<120&&r.height>0&&r.height<80&&ax>0&&ax<150&&ay>0&&ay<140){
                if(!best||ay<best.ay)best={x:Math.round(ax),y:Math.round(ay),ay:ay};}}
          }catch(e){}}return best?JSON.stringify(best):'';})()"""
        try:
            loc = self._eval(js)
            if loc:
                b = json.loads(loc)
                self.cdp.touch(int(b["x"]), int(b["y"]))
                return True
        except Exception:  # noqa: BLE001
            pass
        self.cdp.touch(28, 42)  # 兜底：BOSS 导航栏返回箭头固定位
        return True

    def back_to_list(self, max_back: int = 5) -> bool:
        for _ in range(max_back):
            if self._on_list():
                return True
            self._press_back()
            time.sleep(1.1)
        return self._on_list()

    # ---- 新职位 feed（聊天→新职位）----
    def _on_new_jobs(self) -> bool:
        """前台是可投递职位卡列表（非会话/详情，且有在屏可点卡）。"""
        return not self._on_chat() and not self._on_detail() and len(self.scrape_page()) >= 1

    def goto_new_jobs(self) -> bool:
        self._touch_text(["聊天", "消息"], wait=1.5)
        self._touch_text(["新职位"], wait=1.5)
        for _ in range(4):
            if self._on_new_jobs():
                return True
            time.sleep(0.8)
        return self._on_new_jobs()

    def ensure_on_new_jobs(self) -> bool:
        if self._on_new_jobs():
            return True
        return self.goto_new_jobs()

    def back_to_new_jobs(self, max_back: int = 4) -> bool:
        """投递/查看后返回新职位 feed：先按返回键退出会话/详情（**保留 feed 不刷新**，
        修 P0#3 + 投递后卡死），回到聊天页后确保在「新职位」子tab。"""
        # 1) 退出会话/详情，退栈回到聊天页
        for _ in range(max_back):
            if not self._on_chat() and not self._on_detail():
                break
            self._press_back()
            time.sleep(1.2)
        # 2) 确保「新职位」子tab（有在屏可点卡即就绪）
        for _ in range(2):
            if self._on_new_jobs():
                return True
            self._touch_text(["新职位"], wait=1.5)
        return self._on_new_jobs() or self.goto_new_jobs()

    # ---- 巡检（消息页）----
    def open_message_tab(self) -> bool:
        self._touch_text(["聊天", "消息"], wait=1.5)
        try:
            return bool(self._eval(
                r"""(function(){var f=document.querySelectorAll('iframe');for(var i=0;i<f.length;i++){
                  try{var d=f[i].contentDocument;if(d&&/全部|新招呼|仅沟通/.test(d.body?d.body.innerText:''))return true;}catch(e){}}return false;})()"""))
        except Exception:  # noqa: BLE001
            return False

    def scrape_conversations(self) -> list[dict[str, str]]:
        # M3 完善：暂返回空（不阻塞投递主线）
        return []

    def back_to_job_tab(self) -> None:
        self._touch_text(["职位"], wait=1.5)
