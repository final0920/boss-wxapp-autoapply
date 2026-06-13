"""BOSS直聘 微信小程序驱动 —— 截图 + 本地 OCR(RapidOCR) + SendInput（非侵入）。

与 ms 的 BossDriver 同一套契约（runner/dispatcher/inbox_watcher 依赖）。感知层用
本地 OCR（app/desktop/ocr.py）替代 gpt-5.5 视觉：每屏 ~1s、离线、免费、确定性强；
文字带坐标 → 既识字又定位按钮/tab。决策权仍在 pipeline，本类只观测+执行。

页面快照 dump() 返回 OCR 文本框列表（read_chat_button_label/scrape_detail_fields
接收它）；需要点击的方法各自重新截图取坐标。点击目标用 OCR 文字框中心。
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from app.desktop import capture, input as desk_input, ocr, window
from app.desktop.ocr import TextBox
from app.pipeline.collector import RawJob

logger = logging.getLogger(__name__)

_VERIFY_KW = ("验证码", "拖动", "滑块", "请完成", "安全验证", "向右滑", "点击验证", "拼图", "人机")
_CHAT_KW = ("发送", "说点什么", "由你发起", "请输入", "换一换")


@dataclass
class JobCard:
    """列表页一张卡片：RawJob + 进入详情的归一化点击坐标(0-1000)。"""
    raw: RawJob
    cx: int
    cy: int


class BossWxappDriver:
    """单个 BOSS小程序窗口上的操作。dump=OCR 文本框，定位/读取走 OCR，动作走 SendInput。"""

    def __init__(self, serial: str = "") -> None:
        self.serial = serial
        self._hwnd: Optional[int] = None

    # ------------------------------------------------------------------
    # 窗口 / 快照
    # ------------------------------------------------------------------
    @property
    def hwnd(self) -> int:
        if self._hwnd is None:
            raise RuntimeError("窗口未就绪：先调用 prepare_device()")
        return self._hwnd

    def prepare_device(self) -> None:
        """定位并置顶 BOSS小程序窗口。"""
        wi = window.find_miniprogram_window()
        if wi is None:
            raise RuntimeError("未找到 BOSS直聘 小程序窗口：请在微信中打开该小程序")
        self._hwnd = wi.hwnd
        window.foreground(wi.hwnd)
        time.sleep(0.6)

    def _snapshot(self) -> Optional[tuple[list[TextBox], int, int]]:
        """截图 + OCR → (boxes, w, h)；失败返回 None。"""
        try:
            img = capture.capture_window(self.hwnd)
        except Exception as e:  # noqa: BLE001
            logger.warning("截图失败: %s", e)
            return None
        w, h = img.size
        return ocr.ocr_boxes(img), w, h

    def dump(self) -> Optional[list[TextBox]]:
        """页面快照 = OCR 文本框列表。"""
        snap = self._snapshot()
        return snap[0] if snap else None

    def _click_box(self, b: TextBox, w: int, h: int, settle: float = 1.2) -> None:
        cx, cy = ocr.norm(b, w, h)
        desk_input.click_norm(self.hwnd, cx, cy, settle_sec=settle)

    # ------------------------------------------------------------------
    # 页面判定
    # ------------------------------------------------------------------
    def _is_detail(self, boxes: list[TextBox]) -> bool:
        return ocr.has(boxes, "职位详情") or ocr.has(boxes, "立即沟通", "继续沟通")

    def _is_list(self, boxes: list[TextBox]) -> bool:
        return len(ocr.salary_boxes(boxes)) >= 2 and ocr.has(boxes, "职位") and not self._is_detail(boxes)

    def _is_new_jobs(self, boxes: list[TextBox]) -> bool:
        return (ocr.has(boxes, "新职位") and ocr.has(boxes, "聊天", "消息")
                and len(ocr.salary_boxes(boxes)) >= 1)

    def _is_chat(self, boxes: list[TextBox]) -> bool:
        if ocr.has(boxes, *_CHAT_KW):
            return True
        # 兜底：既不是详情/列表/新职位、也无底部主导航 → 视作会话页
        return (not self._is_detail(boxes) and not self._is_list(boxes)
                and not self._is_new_jobs(boxes) and not ocr.salary_boxes(boxes))

    def _has_bottom_nav(self, boxes: list[TextBox], h: int) -> bool:
        bottom = "".join(b.text for b in boxes if b.cy > h * 0.9)
        return "职位" in bottom and "我的" in bottom and ("聊天" in bottom or "消息" in bottom)

    def detect_verify(self) -> bool:
        snap = self._snapshot()
        return bool(snap and ocr.has(snap[0], *_VERIFY_KW))

    # ------------------------------------------------------------------
    # 列表采集
    # ------------------------------------------------------------------
    def scrape_page(self) -> list[JobCard]:
        snap = self._snapshot()
        if not snap:
            return []
        boxes, w, h = snap
        cards: list[JobCard] = []
        for c in ocr.parse_job_cards(boxes, w, h):
            if not c["title"] or not c["company"]:
                continue
            cards.append(JobCard(
                raw=RawJob(title=c["title"], company=c["company"], salary=c["salary"],
                           area=c["area"], degree=c["degree"], experience=c["experience"],
                           hr_name=c["hr_name"]),
                cx=c["cx"], cy=c["cy"]))
        return cards

    def scroll_list(self) -> None:
        desk_input.scroll(self.hwnd, clicks=-3)

    def _tap_until(self, cx: int, cy: int, target_kw: str = "",
                   retries: int = 3, wait: float = 1.2) -> bool:
        """点击归一化坐标，OCR 校验是否到达目标页；失败重试。"""
        for _ in range(retries):
            desk_input.click_norm(self.hwnd, cx, cy, settle_sec=wait)
            if not target_kw:
                return True
            snap = self._snapshot()
            if not snap:
                continue
            boxes = snap[0]
            if "详情" in target_kw and self._is_detail(boxes):
                return True
            if ocr.has(boxes, target_kw):
                return True
        return False

    # ------------------------------------------------------------------
    # 页面保障 / 返回（职位列表锚点）
    # ------------------------------------------------------------------
    def ensure_on_list(self) -> bool:
        snap = self._snapshot()
        if snap and self._is_list(snap[0]):
            return True
        return self.back_to_list()

    def back_to_list(self, max_back: int = 5) -> bool:
        for _ in range(max_back):
            snap = self._snapshot()
            if snap and self._is_list(snap[0]):
                return True
            desk_input.click_norm(self.hwnd, 50, 50, settle_sec=1.0)  # 左上返回
        self.back_to_job_tab()
        time.sleep(1.2)
        snap = self._snapshot()
        return bool(snap and self._is_list(snap[0]))

    # ------------------------------------------------------------------
    # 新职位 feed（聊天 tab → 新职位 子标签）导航
    # ------------------------------------------------------------------
    def _snap_is_new_jobs(self) -> bool:
        snap = self._snapshot()
        return bool(snap and self._is_new_jobs(snap[0]))

    def goto_new_jobs(self) -> bool:
        """导航到『聊天 tab → 新职位 子标签』。先退出详情/聊天页到带底部主导航的页面。"""
        for _ in range(4):
            snap = self._snapshot()
            if snap and self._has_bottom_nav(snap[0], snap[2]):
                break
            desk_input.click_norm(self.hwnd, 50, 50, settle_sec=1.0)

        # 1. 点底部『聊天/消息』tab
        snap = self._snapshot()
        if snap:
            boxes, w, h = snap
            tab = next((b for b in boxes if b.cy > h * 0.9 and ("聊天" in b.text or "消息" in b.text)), None)
            if tab:
                self._click_box(tab, w, h, 1.5)
            else:
                desk_input.click_norm(self.hwnd, 625, 965, settle_sec=1.5)

        # 2. 点顶部『新职位』子标签
        snap = self._snapshot()
        if snap:
            boxes, w, h = snap
            nj = next((b for b in boxes if b.cy < h * 0.12 and "新职位" in b.text), None)
            if nj:
                self._click_box(nj, w, h, 1.5)
            else:
                desk_input.click_norm(self.hwnd, 430, 32, settle_sec=1.5)

        # 确认（卡片渲染有延迟，重试几次）
        for _ in range(3):
            if self._snap_is_new_jobs():
                return True
            time.sleep(0.8)
        return False

    def ensure_on_new_jobs(self) -> bool:
        if self._snap_is_new_jobs():
            return True
        return self.goto_new_jobs()

    # ------------------------------------------------------------------
    # 详情页字段读取
    # ------------------------------------------------------------------
    def read_chat_button_label(self, detail: list[TextBox]) -> str:
        b = ocr.find_box(detail, "立即沟通", "继续沟通")
        return b.text if b else ""

    def scrape_detail_fields(self, detail: list[TextBox]) -> dict[str, str]:
        """从详情页 OCR 文本框抽取补全字段。"""
        fields = {"location": "", "experience": "", "degree": "",
                  "hr_name": "", "hr_title": "", "hr_active": "", "jd": ""}
        for b in detail:
            t = b.text
            if not fields["location"] and ocr.looks_like_location(t):
                fields["location"] = t
            if not fields["experience"]:
                exp = ocr.match_experience(t)
                if exp:
                    fields["experience"] = exp
            if not fields["degree"] and ocr.is_degree(t):
                fields["degree"] = t
            if not fields["hr_active"] and ("活跃" in t or "回复" in t or "在线" in t):
                fields["hr_active"] = t
            if (not fields["hr_title"] and ocr.name_hint(t) and 2 < len(t) < 24
                    and not ocr.looks_like_location(t)
                    and not re.search(r"\d+\s*[-~]?\s*\d*\s*[Kk]", t)):
                fields["hr_title"] = t
        # JD：详情下半部、较长的文本拼接
        jd_parts = [b.text for b in sorted(detail, key=lambda b: b.cy)
                    if len(b.text) >= 8 and not ocr.looks_like_location(b.text)]
        fields["jd"] = " ".join(jd_parts)[:1500]
        if fields["hr_title"]:
            fields["hr_name"] = fields["hr_title"].split("·")[0].split("•")[0].strip()
        return fields

    # ------------------------------------------------------------------
    # 投递动作
    # ------------------------------------------------------------------
    def _grab_greeting(self, boxes: list[TextBox]) -> str:
        """会话页抓实发招呼语（best-effort：最长的一段非 UI 文本）。"""
        cand = [b.text for b in boxes
                if len(b.text) >= 6 and not ocr.name_hint(b.text)
                and not any(k in b.text for k in _CHAT_KW)]
        return max(cand, key=len) if cand else ""

    def tap_chat_and_capture(self) -> tuple[bool, str, str]:
        """OCR 定位「立即沟通」→ 点击 → 确认进会话页 → 抓招呼语。返回 (ok, greeting, reason)。"""
        snap = self._snapshot()
        if not snap:
            return False, "", "详情页截图失败"
        boxes, w, h = snap
        btn = ocr.find_box(boxes, "立即沟通", "继续沟通")
        if btn is None:
            return False, "", "未找到沟通按钮"

        for _ in range(4):
            self._click_box(btn, w, h, 1.3)
            snap2 = self._snapshot()
            if not snap2:
                continue
            b2, w, h = snap2
            if self._is_chat(b2):
                return True, self._grab_greeting(b2), ""
            nxt = ocr.find_box(b2, "立即沟通", "继续沟通")
            if nxt is None:
                break  # 已离开详情页但未判定为会话——再确认一次
            btn = nxt

        snap3 = self._snapshot()
        if snap3 and self._is_chat(snap3[0]):
            return True, self._grab_greeting(snap3[0]), ""
        return False, "", "未跳转聊天页"

    # ------------------------------------------------------------------
    # 消息 tab 与会话列表
    # ------------------------------------------------------------------
    def open_message_tab(self) -> bool:
        snap = self._snapshot()
        if snap:
            boxes, w, h = snap
            tab = next((b for b in boxes if b.cy > h * 0.9 and ("聊天" in b.text or "消息" in b.text)), None)
            if tab:
                self._click_box(tab, w, h, 1.5)
            else:
                desk_input.click_norm(self.hwnd, 625, 965, settle_sec=1.5)
        snap2 = self._snapshot()
        return bool(snap2 and ocr.has(snap2[0], "全部", "新招呼", "仅沟通", "消息"))

    def scrape_conversations(self) -> list[dict[str, str]]:
        """OCR 解析消息列表页的会话行（best-effort 行分组）。

        每条会话：头像 | 名字(左) + 时间(右上) | 公司|岗位 + 最后消息。
        以"名字行右侧的时间"为行锚，按 y 分组。系统通知（无公司|岗位结构）过滤。
        """
        snap = self._snapshot()
        if not snap:
            return []
        boxes, w, h = snap
        # 时间锚：形如 13:01 / 昨天 / 星期X / N天前
        time_re = re.compile(r"^\d{1,2}:\d{2}$|昨天|前天|星期|周[一二三四五六日]|\d+天前|刚刚")
        anchors = sorted([b for b in boxes if b.cx > w * 0.7 and time_re.search(b.text)],
                         key=lambda b: b.cy)
        convs: list[dict[str, str]] = []
        for i, a in enumerate(anchors):
            top = a.cy - 28
            bot = anchors[i + 1].cy - 28 if i + 1 < len(anchors) else h + 1
            row = [b for b in boxes if top <= b.cy < bot and b.cx < w * 0.72]
            row.sort(key=lambda b: (b.cy, b.cx))
            if not row:
                continue
            name = row[0].text
            rest = [b.text for b in row[1:]]
            position = next((t for t in rest if ("|" in t or "｜" in t)), "")
            others = [t for t in rest if t != position]
            last_msg = max(others, key=len) if others else ""
            status = ""
            for mark in ("[新招呼]", "[送达]", "新招呼", "送达"):
                if any(mark in t for t in rest):
                    status = mark.strip("[]")
                    break
            unread = next((t for t in rest if t.isdigit()), "")
            if not position:
                continue  # 过滤系统通知/官方
            convs.append({"hr_name": name, "position": position, "last_msg": last_msg,
                          "time": a.text, "status": status, "unread": unread})
        return convs

    def back_to_job_tab(self) -> None:
        snap = self._snapshot()
        if snap:
            boxes, w, h = snap
            tab = next((b for b in boxes if b.cy > h * 0.9 and "职位" in b.text and "详情" not in b.text), None)
            if tab:
                self._click_box(tab, w, h, 1.5)
                return
        desk_input.click_norm(self.hwnd, 125, 980, settle_sec=1.5)
