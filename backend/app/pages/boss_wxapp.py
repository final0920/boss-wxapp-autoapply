"""BOSS直聘 微信小程序驱动 —— 截图 + gpt-5.5 VLM 抽取/定位 + SendInput（非侵入）。

与 ms 的 `BossDriver` 实现同一套契约（runner/dispatcher/inbox_watcher 依赖），仅把
"adb 控安卓真机"换成"桌面控小程序窗口"。决策权仍在 pipeline，本类只观测+执行。

G0 已验证（见 .omc/plans/boss-wxapp-autoapply-plan.md §2.5）：窗口定位/截图/列表抽取/
DPI 点击命中。实现进度：
  M1 ✅ 窗口·截图·点击·列表抽取    M2 详情+投递    M3 巡检
未实现方法显式 NotImplementedError 并标注里程碑，保证模块可导入、契约清晰。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from PIL.Image import Image

from app.desktop import capture, input as desk_input, window
from app.llm.client import get_client
from app.pipeline.collector import RawJob

logger = logging.getLogger(__name__)


@dataclass
class JobCard:
    """列表页一张卡片：RawJob + 进入详情的归一化点击坐标(0-1000)。"""
    raw: RawJob
    cx: int
    cy: int


_LIST_PROMPT = (
    "这是 BOSS直聘 微信小程序的截图。判断页面类型并提取当前可见的所有职位卡片。"
    "每张卡片输出 title(职位)、company(公司)、salary、area(地点,可空)、degree(学历,可空)、"
    "experience(经验,可空)、company_scale(规模,可空)、finance_stage(融资,可空)、hr_name(可空)，"
    "以及点击可进入该职位详情的目标坐标 cx、cy（归一化 0-1000，指向职位标题/薪资区，"
    "勿指向技能标签或 HR 行）。严格只输出 JSON："
    '{"page_type":"job_list|job_detail|chat|message_list|other",'
    '"cards":[{"title":"","company":"","salary":"","area":"","degree":"","experience":"",'
    '"company_scale":"","finance_stage":"","hr_name":"","cx":0,"cy":0}]}'
)


class BossWxappDriver:
    """单个 BOSS小程序窗口上的操作。dump=截图，定位/读取走 VLM，动作走 SendInput。"""

    def __init__(self, serial: str = "") -> None:
        self.serial = serial  # 兼容 runner 签名；视觉路线无 serial 概念
        self._hwnd: Optional[int] = None

    # ------------------------------------------------------------------
    # 窗口
    # ------------------------------------------------------------------
    @property
    def hwnd(self) -> int:
        if self._hwnd is None:
            raise RuntimeError("窗口未就绪：先调用 prepare_device()")
        return self._hwnd

    def prepare_device(self) -> None:
        """定位并置顶 BOSS小程序窗口（锚点：职位列表页）。"""
        wi = window.find_miniprogram_window()
        if wi is None:
            raise RuntimeError("未找到 BOSS直聘 小程序窗口：请在微信中打开该小程序")
        self._hwnd = wi.hwnd
        window.foreground(wi.hwnd)
        time.sleep(0.6)
        # TODO(M2): 校验并导航到职位 tab 列表页锚点

    # ------------------------------------------------------------------
    # 截图（dump 等价物）
    # ------------------------------------------------------------------
    def dump(self) -> Optional[Image]:
        """当前窗口截图作为页面快照（VLM 在各方法内解析）。"""
        try:
            return capture.capture_window(self.hwnd)
        except Exception as e:  # noqa: BLE001
            logger.warning("dump 截图失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 列表采集（M1 ✅）
    # ------------------------------------------------------------------
    def scrape_page(self) -> list[JobCard]:
        img = self.dump()
        if img is None:
            return []
        try:
            data = get_client().vision_json(img, _LIST_PROMPT)
        except Exception as e:  # noqa: BLE001
            logger.warning("scrape_page VLM 失败: %s", e)
            return []
        cards: list[JobCard] = []
        for c in data.get("cards", []):
            title = (c.get("title") or "").strip()
            company = (c.get("company") or "").strip()
            if not title or not company:
                continue
            cards.append(JobCard(
                raw=RawJob(
                    title=title, company=company,
                    salary=(c.get("salary") or "").strip(),
                    area=(c.get("area") or "").strip(),
                    degree=(c.get("degree") or "").strip(),
                    experience=(c.get("experience") or "").strip(),
                    company_scale=(c.get("company_scale") or "").strip(),
                    finance_stage=(c.get("finance_stage") or "").strip(),
                    hr_name=(c.get("hr_name") or "").strip(),
                ),
                cx=int(c.get("cx", 500)), cy=int(c.get("cy", 500)),
            ))
        return cards

    def scroll_list(self) -> None:
        desk_input.scroll(self.hwnd, clicks=-3)

    def _tap_until(self, cx: int, cy: int, target_kw: str = "",
                   retries: int = 3, wait: float = 1.2) -> bool:
        """点击归一化坐标，截图 VLM 校验是否到达 target_kw 指示页面；失败重试。"""
        _verify_prompt = (
            f"这是 BOSS直聘 微信小程序截图。判断当前页面是否已到达含关键词「{target_kw}」的目标页面。"
            '严格只输出 JSON：{"reached": true}或{"reached": false}'
        )
        for attempt in range(retries):
            desk_input.click_norm(self.hwnd, cx, cy, settle_sec=wait)
            if not target_kw:
                return True
            img = self.dump()
            if img is None:
                continue
            try:
                data = get_client().vision_json(img, _verify_prompt)
                if data.get("reached"):
                    return True
            except Exception as e:  # noqa: BLE001
                logger.warning("_tap_until VLM 校验失败(attempt %d): %s", attempt, e)
        return False

    # ------------------------------------------------------------------
    # M2：验证码检测 / 页面保障
    # ------------------------------------------------------------------

    def detect_verify(self) -> bool:
        """VLM 判断当前是否为验证码/风控页。"""
        img = self.dump()
        if img is None:
            return False
        _prompt = (
            "这是 BOSS直聘 微信小程序截图。判断当前是否显示验证码、滑块、图片拼图、"
            "风控提示或安全校验页面（任何需要手动操作才能继续的拦截页）。"
            '严格只输出 JSON：{"is_verify": true}或{"is_verify": false}'
        )
        try:
            data = get_client().vision_json(img, _prompt)
            return bool(data.get("is_verify", False))
        except Exception as e:  # noqa: BLE001
            logger.warning("detect_verify VLM 失败: %s", e)
            return False

    def back_to_list(self, max_back: int = 5) -> bool:
        """逐次点返回键直到 VLM 确认到达职位列表页；兜底重新导航到职位 tab。

        VLM 判据：page_type == 'job_list'（复用 _LIST_PROMPT 结构）。
        """
        _list_check_prompt = (
            "这是 BOSS直聘 微信小程序截图。只需判断当前是否为职位列表页"
            "（显示多张职位卡片的滚动列表）。"
            '严格只输出 JSON：{"page_type":"job_list"}或{"page_type":"other"}'
        )

        def _on_list() -> bool:
            img = self.dump()
            if img is None:
                return False
            try:
                data = get_client().vision_json(img, _list_check_prompt)
                return data.get("page_type") == "job_list"
            except Exception as e:  # noqa: BLE001
                logger.warning("back_to_list VLM 检查失败: %s", e)
                return False

        for _ in range(max_back):
            if _on_list():
                return True
            # 点左上角返回箭头（归一化坐标约 (50, 50)，小程序通用返回区）
            desk_input.click_norm(self.hwnd, 50, 50, settle_sec=1.0)
        if _on_list():
            return True
        # 兜底：尝试点底部"职位"tab 回锚点
        logger.warning("back_to_list 返回键未能回到列表，兜底点职位 tab")
        self.back_to_job_tab()
        time.sleep(1.5)
        return _on_list()

    def ensure_on_list(self) -> bool:
        """VLM 判断当前页，已在列表则直接返回 True，否则调 back_to_list 恢复。"""
        _list_check_prompt = (
            "这是 BOSS直聘 微信小程序截图。只需判断当前是否为职位列表页"
            "（显示多张职位卡片的滚动列表）。"
            '严格只输出 JSON：{"page_type":"job_list"}或{"page_type":"other"}'
        )
        img = self.dump()
        if img is None:
            return self.back_to_list()
        try:
            data = get_client().vision_json(img, _list_check_prompt)
            if data.get("page_type") == "job_list":
                return True
        except Exception as e:  # noqa: BLE001
            logger.warning("ensure_on_list VLM 失败: %s", e)
        return self.back_to_list()

    # ------------------------------------------------------------------
    # M2：详情页字段读取
    # ------------------------------------------------------------------

    def read_chat_button_label(self, detail: Image) -> str:
        """VLM 读详情页「立即沟通」或「继续沟通」按钮文案；未找到返回空串。"""
        _prompt = (
            "这是 BOSS直聘 微信小程序职位详情页截图。找到页面底部的沟通按钮，"
            "读取其文案（通常是「立即沟通」或「继续沟通」）。"
            '严格只输出 JSON：{"label":"立即沟通"}，若未找到则{"label":""}'
        )
        try:
            data = get_client().vision_json(detail, _prompt)
            return (data.get("label") or "").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("read_chat_button_label VLM 失败: %s", e)
            return ""

    def scrape_detail_fields(self, detail: Image) -> dict[str, str]:
        """VLM 从详情页截图抽取补全字段（location/experience/degree/hr_name/hr_title/hr_active/jd）。"""
        _prompt = (
            "这是 BOSS直聘 微信小程序职位详情页截图。提取以下字段："
            "location(工作地点，如「武汉·洪山区·光谷」)、"
            "experience(经验要求，如「1-3年」)、"
            "degree(学历要求，如「本科」)、"
            "hr_name(HR姓名，如「刘女士」)、"
            "hr_title(HR职务，如「公司 • 人事专员」)、"
            "hr_active(HR活跃状态，如「17分钟前回复」)、"
            "jd(职位描述全文，尽量完整)。"
            "严格只输出 JSON："
            '{"location":"","experience":"","degree":"","hr_name":"","hr_title":"","hr_active":"","jd":""}'
        )
        empty: dict[str, str] = {
            "location": "", "experience": "", "degree": "",
            "hr_name": "", "hr_title": "", "hr_active": "", "jd": "",
        }
        try:
            data = get_client().vision_json(detail, _prompt)
            return {k: (data.get(k) or "").strip() for k in empty}
        except Exception as e:  # noqa: BLE001
            logger.warning("scrape_detail_fields VLM 失败: %s", e)
            return empty

    def tap_chat_and_capture(self) -> tuple[bool, str, str]:
        """VLM 定位「立即沟通」→ click_norm → VLM 确认进会话页 → VLM 抓实发招呼语。

        返回 (ok, greeting, fail_reason)。前置：当前停在目标岗位详情页。
        """
        img = self.dump()
        if img is None:
            return False, "", "详情页截图失败"

        # 定位沟通按钮坐标
        _locate_prompt = (
            "这是 BOSS直聘 微信小程序职位详情页截图。定位页面底部「立即沟通」或「继续沟通」按钮的中心坐标。"
            "坐标归一化到 0-1000（0=左/上，1000=右/下）。"
            '严格只输出 JSON：{"found":true,"cx":500,"cy":900}，若未找到则{"found":false,"cx":0,"cy":0}'
        )
        try:
            loc = get_client().vision_json(img, _locate_prompt)
        except Exception as e:  # noqa: BLE001
            logger.warning("tap_chat_and_capture 定位失败: %s", e)
            return False, "", f"VLM 定位按钮失败: {e}"

        if not loc.get("found"):
            return False, "", "未找到沟通按钮"

        cx, cy = int(loc.get("cx", 500)), int(loc.get("cy", 900))

        # 点击并等待页面变化
        _chat_check_prompt = (
            "这是 BOSS直聘 微信小程序截图。判断当前是否已进入与 HR 的聊天会话页面"
            "（页面顶部显示 HR 名字，页面中有消息气泡，底部有输入框）。"
            '严格只输出 JSON：{"in_chat":true}或{"in_chat":false}'
        )
        entered = False
        for attempt in range(4):
            desk_input.click_norm(self.hwnd, cx, cy, settle_sec=1.2)
            after = self.dump()
            if after is None:
                continue
            try:
                chk = get_client().vision_json(after, _chat_check_prompt)
                if chk.get("in_chat"):
                    entered = True
                    break
            except Exception as e:  # noqa: BLE001
                logger.warning("tap_chat_and_capture 会话确认失败(attempt %d): %s", attempt, e)

        if not entered:
            return False, "", "未跳转聊天页"

        # 抓实发招呼语
        chat_img = self.dump()
        greeting = ""
        if chat_img is not None:
            _greeting_prompt = (
                "这是 BOSS直聘 微信小程序聊天会话页截图。找到页面中最后一条由「我」发出的消息气泡文本，"
                "即招呼语（通常是第一条消息）。"
                '严格只输出 JSON：{"greeting":"<消息内容>"}，若未找到则{"greeting":""}'
            )
            try:
                g = get_client().vision_json(chat_img, _greeting_prompt)
                greeting = (g.get("greeting") or "").strip()
            except Exception as e:  # noqa: BLE001
                logger.warning("tap_chat_and_capture 抓招呼语失败: %s", e)

        return True, greeting, ""

    # ------------------------------------------------------------------
    # M3：消息 tab 与会话列表
    # ------------------------------------------------------------------

    def open_message_tab(self) -> bool:
        """VLM 定位底部「消息/聊天」tab → click_norm → VLM 确认到达消息列表页。"""
        img = self.dump()
        if img is None:
            return False

        _locate_prompt = (
            "这是 BOSS直聘 微信小程序截图。定位页面底部导航栏中「消息」或「聊天」tab 的中心坐标。"
            "坐标归一化到 0-1000。"
            '严格只输出 JSON：{"found":true,"cx":750,"cy":980}，若未找到则{"found":false,"cx":750,"cy":980}'
        )
        try:
            loc = get_client().vision_json(img, _locate_prompt)
        except Exception as e:  # noqa: BLE001
            logger.warning("open_message_tab 定位失败: %s，用默认坐标", e)
            loc = {"found": False, "cx": 750, "cy": 980}

        cx, cy = int(loc.get("cx", 750)), int(loc.get("cy", 980))
        desk_input.click_norm(self.hwnd, cx, cy, settle_sec=1.5)

        # VLM 确认到位：消息列表页特征（会话列表，顶部搜索框）
        after = self.dump()
        if after is None:
            return False
        _check_prompt = (
            "这是 BOSS直聘 微信小程序截图。判断当前是否已到达消息/聊天列表页"
            "（页面显示与 HR 的会话列表，顶部有搜索框）。"
            '严格只输出 JSON：{"on_message":true}或{"on_message":false}'
        )
        try:
            chk = get_client().vision_json(after, _check_prompt)
            return bool(chk.get("on_message", False))
        except Exception as e:  # noqa: BLE001
            logger.warning("open_message_tab 确认失败: %s", e)
            return False

    def scrape_conversations(self) -> list[dict[str, str]]:
        """VLM 解析当前消息列表页的会话列表。

        返回 [{hr_name, position, last_msg, time, status, unread}]。
        position 形如「公司 | 岗位」；系统通知项（无 position）已过滤。
        """
        img = self.dump()
        if img is None:
            return []
        _prompt = (
            "这是 BOSS直聘 微信小程序消息列表页截图。提取所有与 HR 的会话条目。"
            "每条会话输出：hr_name(HR姓名)、position(格式「公司 | 岗位」)、"
            "last_msg(最后一条消息摘要)、time(消息时间，如「13:01」或「昨天」)、"
            "status(消息状态标签，如「[新招呼]」或「[送达]」，无则空)、"
            "unread(未读数字字符串，无则空)。"
            "过滤掉系统通知、官方公告等非真实 HR 会话（这类条目通常没有 position 字段）。"
            '严格只输出 JSON：{"conversations":[{"hr_name":"","position":"","last_msg":"","time":"","status":"","unread":""}]}'
        )
        try:
            data = get_client().vision_json(img, _prompt)
        except Exception as e:  # noqa: BLE001
            logger.warning("scrape_conversations VLM 失败: %s", e)
            return []
        convs: list[dict[str, str]] = []
        for c in data.get("conversations", []):
            position = (c.get("position") or "").strip()
            if not position:
                continue  # 过滤系统通知
            convs.append({
                "hr_name": (c.get("hr_name") or "").strip(),
                "position": position,
                "last_msg": (c.get("last_msg") or "").strip(),
                "time": (c.get("time") or "").strip(),
                "status": (c.get("status") or "").strip(),
                "unread": (c.get("unread") or "").strip(),
            })
        return convs

    def back_to_job_tab(self) -> None:
        """VLM 定位底部「职位」tab → click_norm，回到职位列表锚点。"""
        img = self.dump()
        _locate_prompt = (
            "这是 BOSS直聘 微信小程序截图。定位页面底部导航栏中「职位」tab 的中心坐标。"
            "坐标归一化到 0-1000。"
            '严格只输出 JSON：{"found":true,"cx":125,"cy":980}，若未找到则{"found":false,"cx":125,"cy":980}'
        )
        cx, cy = 125, 980  # 默认兜底坐标
        if img is not None:
            try:
                loc = get_client().vision_json(img, _locate_prompt)
                cx, cy = int(loc.get("cx", cx)), int(loc.get("cy", cy))
            except Exception as e:  # noqa: BLE001
                logger.warning("back_to_job_tab 定位失败: %s，用默认坐标", e)
        desk_input.click_norm(self.hwnd, cx, cy, settle_sec=1.5)
