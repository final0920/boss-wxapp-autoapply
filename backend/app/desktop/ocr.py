"""本地 OCR 感知层 —— RapidOCR（ONNX，中文）替代 gpt-5.5 视觉。

为什么（用户反馈 + 实测）：每卡 ~10 次 VLM 调用 → ~90s/卡，太慢且烧 token。
RapidOCR 单屏 ~1s、离线、免费、确定性强；文字带坐标框 → 既识字又定位，
连按钮/tab 都靠 OCR 文字框定位，无需 VLM。

用法：
    boxes = ocr_boxes(pil_image)         # 一次 OCR
    b = find_box(boxes, "立即沟通", "继续沟通")   # 找按钮
    cards = parse_job_cards(boxes, w, h) # 列表卡片 → dict（含归一化点击坐标）
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass

import numpy as np
from PIL.Image import Image

_engine = None
_engine_lock = threading.Lock()


def _ocr():
    """RapidOCR 单例（首次加载模型 ~1-2s）。"""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR()
    return _engine


@dataclass
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def ocr_boxes(image: Image) -> list[TextBox]:
    """对 PIL 图做 OCR，返回文本框列表（含坐标、置信度）。"""
    arr = np.asarray(image.convert("RGB"))
    result, _ = _ocr()(arr)
    out: list[TextBox] = []
    for box, text, score in (result or []):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        t = (text or "").strip()
        if t:
            out.append(TextBox(t, min(xs), min(ys), max(xs), max(ys), float(score)))
    return out


# ---------------------------------------------------------------------------
# 查找 helpers
# ---------------------------------------------------------------------------
def find_box(boxes: list[TextBox], *keywords: str) -> TextBox | None:
    """返回第一个文本含任一关键词的框（按出现顺序）。"""
    for b in boxes:
        if any(k in b.text for k in keywords):
            return b
    return None


def has(boxes: list[TextBox], *keywords: str) -> bool:
    return find_box(boxes, *keywords) is not None


def norm(b: TextBox, w: int, h: int) -> tuple[int, int]:
    """文本框中心 → 归一化 0-1000（供 desktop.input.click_norm）。"""
    return int(b.cx / w * 1000), int(b.cy / h * 1000)


# ---------------------------------------------------------------------------
# 列表卡片解析（新职位 / 职位列表通用，布局一致）
# ---------------------------------------------------------------------------
_SAL = re.compile(r"\d+\s*[-~]\s*\d+\s*[Kk]|\d+\s*[Kk]\b")
_DEGREE = ("学历不限", "初中及以下", "中专", "中技", "高中", "大专", "本科", "硕士", "博士")
_EXP = re.compile(r"\d+-?\d*年(以上|以内)?|经验不限|应届|在校")
_NAME_HINT = ("·", "HR", "女士", "先生", "经理", "Manager", "招聘", "总裁", "总经理",
              "老板", "主管", "总监", "猎头", "人事", "专员", "BOSS", "CEO", "CTO")
_CITY = ("北京", "上海", "广州", "深圳", "杭州", "武汉", "成都", "南京", "西安", "苏州",
         "天津", "重庆", "长沙", "郑州", "合肥", "东莞", "佛山", "宁波", "青岛", "无锡",
         "厦门", "福州", "济南", "大连", "沈阳", "昆明", "南昌", "贵阳", "南宁")


def parse_job_cards(boxes: list[TextBox], w: int, h: int) -> list[dict]:
    """把 OCR 文本框按布局拼成职位卡片列表。

    以"薪资行"为每张卡的锚点；title 取薪资同行左侧最长文本，company/hr/area
    按相对位置取。degree/experience 从标签推断（列表常缺，详情页补全）。
    返回 [{title,salary,company,area,degree,experience,hr_name,cx,cy}]，
    cx/cy 为归一化点击坐标（指向标题，点击进详情）。
    """
    sals = sorted([b for b in boxes if _SAL.search(b.text)], key=lambda b: b.cy)
    cards: list[dict] = []
    for i, s in enumerate(sals):
        top = s.cy - 35
        bot = sals[i + 1].cy - 35 if i + 1 < len(sals) else h + 1
        band = [b for b in boxes if top <= b.cy < bot]

        # 标题：薪资同行、在薪资左侧、最长文本
        same_row = [b for b in band if abs(b.cy - s.cy) < 28 and b.cx < s.cx]
        title = max(same_row, key=lambda b: len(b.text), default=None)
        if title is None:
            continue
        ty = title.cy

        # 公司：标题下一行、左对齐第一个（避开标题换行的第二行——含括号收尾的跳过）
        below_left = sorted(
            [b for b in band if b.cy > ty + 18 and b.x0 < 240
             and not b.text.endswith(("）", ")"))],
            key=lambda b: b.cy)
        company = below_left[0].text if below_left else ""

        # HR：靠卡片下部、含人名特征
        hr_box = next((b for b in band if b.cy > ty + 70 and any(k in b.text for k in _NAME_HINT)), None)
        hr_name = hr_box.text.split("·")[0].split("•")[0].strip() if hr_box else ""

        # 地点：HR 同行右侧的城市；兜底全卡找城市词
        area = ""
        if hr_box is not None:
            cand = [b for b in band if abs(b.cy - hr_box.cy) < 22 and b.cx > 460 and b.text != "new"]
            area = next((b.text for b in cand if any(c in b.text for c in _CITY)), "")
            if not area and cand:
                area = cand[0].text
        if not area:
            cb = next((b for b in band if any(c in b.text for c in _CITY)), None)
            area = cb.text if cb else ""

        tags = [b.text for b in band if b.cy > ty + 18 and b.cy < (hr_box.cy - 10 if hr_box else bot)]
        degree = next((t for t in tags if t in _DEGREE), "")
        experience = next((t for t in tags if _EXP.fullmatch(t)), "")

        cx, cy = norm(title, w, h)
        cards.append({
            "title": title.text, "salary": s.text, "company": company, "area": area,
            "degree": degree, "experience": experience, "hr_name": hr_name,
            "cx": cx, "cy": cy,
        })
    return cards


# ---------------------------------------------------------------------------
# 详情页字段 helpers（供 scrape_detail_fields）
# ---------------------------------------------------------------------------
def salary_boxes(boxes: list[TextBox]) -> list[TextBox]:
    return [b for b in boxes if _SAL.search(b.text)]


def looks_like_location(t: str) -> bool:
    """形如「武汉·江汉区·常青」：含城市 + 分隔点。"""
    return ("·" in t or "·" in t) and any(c in t for c in _CITY)


def match_experience(t: str) -> str:
    m = _EXP.search(t)
    return m.group(0) if (m and len(t) < 14) else ""


def is_degree(t: str) -> str:
    return t if t in _DEGREE else ""


def name_hint(t: str) -> bool:
    return any(k in t for k in _NAME_HINT)
