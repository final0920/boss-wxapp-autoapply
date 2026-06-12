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
        """点击窗口内归一化坐标并等待页面切换。

        M1：执行点击。TODO(M2)：截图 VLM 校验是否到达 target_kw 指示页面。
        """
        for _ in range(retries):
            desk_input.click_norm(self.hwnd, cx, cy, settle_sec=wait)
            return True  # TODO(M2): VLM 校验 target_kw
        return False

    # ------------------------------------------------------------------
    # M2/M3 契约占位（未实现）
    # ------------------------------------------------------------------
    def detect_verify(self) -> bool:
        return False  # TODO(M2): VLM 识别验证码/风控页

    def ensure_on_list(self) -> bool:
        return True   # TODO(M2): VLM 判断当前页，非列表则返回/重进

    def read_chat_button_label(self, detail) -> str:
        raise NotImplementedError("M2: VLM 读「立即沟通/继续沟通」按钮文案")

    def scrape_detail_fields(self, detail) -> dict[str, str]:
        raise NotImplementedError("M2: VLM 抽详情页字段(JD/地点/经验/学历/HR)")

    def tap_chat_and_capture(self) -> tuple[bool, str, str]:
        raise NotImplementedError("M2: VLM 定位「立即沟通」→点击→确认会话→抓招呼语")

    def back_to_list(self) -> bool:
        raise NotImplementedError("M2: 返回列表页锚点")

    def open_message_tab(self) -> bool:
        raise NotImplementedError("M3: 切到消息页")

    def back_to_job_tab(self) -> None:
        raise NotImplementedError("M3: 切回职位 tab")

    def scrape_conversations(self) -> list[dict[str, str]]:
        raise NotImplementedError("M3: VLM 解析会话列表")
