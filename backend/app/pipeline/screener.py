"""
screener — 纯函数筛选层（§3/§7，去 LangGraph）。

公开接口：
  parse_salary(s)       -> (min_k, max_k)
  parse_degree(s)       -> int
  parse_experience(s)   -> int
  parse_hr_active(s)    -> int | None
  prefilter(job, rules) -> (passed: bool, fail_reason: str)
  screen(job, rules)    -> ScreenResult
  apply_screen_result(session, application_id, result) -> None

"是否投递"决策权仅属此模块。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.models import Application, ApplicationStatus, Job
from app.rules import RulesConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 学历序级表（越大越高）
# ---------------------------------------------------------------------------

_DEGREE_ORDER: dict[str, int] = {
    "不限": 0,
    "高中": 1,
    "中专": 2,
    "中技": 2,
    "大专": 3,
    "本科": 4,
    "硕士": 5,
    "博士": 6,
}


def _degree_level(s: str) -> int:
    """从学历字符串提取序级；匹配最高序级（处理复合描述如'本科及以上'）。"""
    if not s:
        return 0
    best = 0
    for key, val in _DEGREE_ORDER.items():
        if key in s and val > best:
            best = val
    return best


# ---------------------------------------------------------------------------
# 解析器
# ---------------------------------------------------------------------------


def parse_salary(s: str) -> tuple[float, float]:
    """解析薪资字符串，返回 (min_k, max_k)。解析失败或面议返回 (0, 0)。

    示例:
      "10-15K·13薪"       -> (10.0, 15.0)
      "2000-150000元/月"   -> (2.0, 150.0)   # 元/月 -> K
      "20-30K"             -> (20.0, 30.0)
      "面议"               -> (0.0, 0.0)
      None / ""            -> (0.0, 0.0)
    """
    if not s:
        return (0.0, 0.0)
    if "面议" in s:
        return (0.0, 0.0)

    # 匹配 K/k 单位的区间，如 "10-15K" 或 "10K-15K"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Kk]?\s*[-~]\s*(\d+(?:\.\d+)?)\s*[Kk]", s, re.IGNORECASE)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        # 判断是否是 K 单位（后面有 K 标记）
        if re.search(r"\d\s*[Kk]", s, re.IGNORECASE):
            return (lo, hi)
        # 否则可能是元/月
        # 若数字 > 500 则视为元，转 K
        if hi > 500:
            return (round(lo / 1000, 2), round(hi / 1000, 2))
        return (lo, hi)

    # 匹配 元/月 格式，如 "2000-150000元/月"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*元", s)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (round(lo / 1000, 2), round(hi / 1000, 2))

    # 单值 K，如 "15K"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[Kk]", s, re.IGNORECASE)
    if m:
        v = float(m.group(1))
        return (v, v)

    return (0.0, 0.0)


def parse_degree(s: str) -> int:
    """将学历字符串映射为整数序级。空/不限 -> 0；无法识别 -> 0（放行）。"""
    return _degree_level(s)


def parse_experience(s: str) -> int:
    """解析经验要求，返回最低年限整数。

    示例:
      "1-3年"     -> 1
      "3-5年"     -> 3
      "10年以上"  -> 10
      "经验不限"  -> 0
      "应届"      -> 0
      ""          -> 0
    """
    if not s:
        return 0
    if any(kw in s for kw in ("不限", "应届", "在校")):
        return 0
    # "10年以上" / "10年+"
    m = re.search(r"(\d+)\s*年\s*以上", s)
    if m:
        return int(m.group(1))
    # "1-3年"
    m = re.search(r"(\d+)\s*[-~]\s*\d+\s*年", s)
    if m:
        return int(m.group(1))
    # 纯 "3年"
    m = re.search(r"(\d+)\s*年", s)
    if m:
        return int(m.group(1))
    return 0


def parse_hr_active(s: str) -> Optional[int]:
    """解析 HR 活跃度字符串，返回天数；无法判断返回 None。

    映射：
      在线/刚刚/今日 -> 1
      3日内          -> 3
      本周           -> 7
      本月           -> 30
      其他（更久）   -> 999
      空/None        -> None
    """
    if not s:
        return None
    s_lower = s.strip()
    # 真机实测格式（D0）：'今日回复10+次'、'17分钟前回复 | 今日回复10+次'
    if re.search(r"(分钟|小时)前", s_lower):
        return 1
    if any(kw in s_lower for kw in ("在线", "刚刚", "今日", "今天")):
        return 1
    if "昨日" in s_lower or "昨天" in s_lower:
        return 2
    if "周内" in s_lower:
        return 7
    if "月内" in s_lower:
        return 30
    if re.search(r"[13]\s*日", s_lower):
        # 区分 "3日内" vs "本月" 等
        m = re.search(r"(\d+)\s*日", s_lower)
        if m:
            days = int(m.group(1))
            if days <= 7:
                return days
    if "本周" in s_lower or "一周" in s_lower:
        return 7
    if "本月" in s_lower or "一个月" in s_lower:
        return 30
    # 有任何"活跃"相关词但不能具体解析 -> 999（保守）
    return 999


# ---------------------------------------------------------------------------
# 列表级预过滤
# ---------------------------------------------------------------------------


def _salary_intersects(
    job_min: float, job_max: float, rule_min: float, rule_max: float
) -> bool:
    """判断薪资区间是否相交（0 表示不限，放行）。"""
    # job 解析失败 (0,0) -> 放行
    if job_min == 0 and job_max == 0:
        return True
    # 规则不限 -> 放行
    if rule_min == 0 and rule_max == 0:
        return True
    # 单边上限 0 -> 无上限
    eff_job_max = job_max if job_max > 0 else float("inf")
    eff_rule_max = rule_max if rule_max > 0 else float("inf")
    # 区间相交：不是"job 全在 rule 左边" 也不是"job 全在 rule 右边"
    return not (eff_job_max < rule_min or job_min > eff_rule_max)


def prefilter(job: Job, rules: RulesConfig) -> tuple[bool, str]:
    """列表级快速过滤（无需网络/LLM）。

    返回 (passed, fail_reason)。passed=True 时 fail_reason=""。
    """
    # 1. 薪资区间相交
    job_min, job_max = parse_salary(job.salary)
    if not _salary_intersects(job_min, job_max, rules.salary_min_k, rules.salary_max_k):
        return (False, f"薪资不匹配: {job.salary}")

    # 2. allowed_cities：包含匹配 job.area
    if rules.allowed_cities and job.area:
        if not any(city in job.area for city in rules.allowed_cities):
            return (False, f"城市不匹配: {job.area}")

    # 3. blocked_areas：包含匹配 job.area
    if rules.blocked_areas and job.area:
        for ba in rules.blocked_areas:
            if ba in job.area:
                return (False, f"区域黑名单: {job.area}")

    # 4. include_keywords 不在列表级判定——列表页抓不到 JD，标题不含关键词
    #    不代表 JD 不含（如标题'后端开发工程师'、JD 全是 Java/AI）。
    #    必含关键词统一在详情级 _check_detail_hard 对 title+jd 判定，避免误杀。

    # 5. exclude_keywords：对 title+company（大小写不敏感）
    for kw in rules.exclude_keywords:
        kw_l = kw.lower()
        if kw_l in job.title.lower() or kw_l in job.company.lower():
            return (False, f"命中排除关键词: {kw}")

    # 6. 列表级 degree（字段非空才判）
    if rules.my_degree and job.degree:
        job_degree_level = parse_degree(job.degree)
        my_level = parse_degree(rules.my_degree)
        if my_level > 0 and job_degree_level > my_level:
            return (False, f"学历要求过高: {job.degree}")

    # 7. 列表级 experience（字段非空才判）
    if rules.my_experience_years > 0 and job.experience:
        required = parse_experience(job.experience)
        if required > rules.my_experience_years:
            return (False, f"经验要求过高: {job.experience}")

    return (True, "")


# ---------------------------------------------------------------------------
# 详情级筛选结果
# ---------------------------------------------------------------------------


@dataclass
class ScreenResult:
    passed_hard: bool = False
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    final: str = "FAILED"        # "CLAIMED" | "FAILED"
    fail_reason: str = ""
    llm_unavailable: bool = False  # LLM 调用失败（如 403）；区别于"分数不够"


# ---------------------------------------------------------------------------
# 详情级过滤 + LLM 打分
# ---------------------------------------------------------------------------


def _check_detail_hard(job: Job, rules: RulesConfig) -> tuple[bool, str, list[str]]:
    """详情级硬过滤。返回 (passed, fail_reason, missing_notes)。"""
    missing: list[str] = []

    # exclude_keywords：作用域扩展到 jd（大小写不敏感）
    for kw in rules.exclude_keywords:
        kw_l = kw.lower()
        if kw_l in job.title.lower() or kw_l in job.company.lower() or kw_l in job.jd.lower():
            return (False, f"命中排除关键词: {kw}", missing)

    # include_keywords：详情级含 title+jd（大小写不敏感）
    if rules.include_keywords:
        combined = (job.title + job.jd).lower()
        if not any(kw.lower() in combined for kw in rules.include_keywords):
            return (False, "标题/JD 未含必须关键词", missing)

    # company_scales
    if rules.company_scales:
        if not job.company_scale:
            missing.append("missing:company_scale")
        else:
            if not any(scale in job.company_scale for scale in rules.company_scales):
                return (False, f"公司规模不符: {job.company_scale}", missing)

    # my_degree
    if rules.my_degree:
        if not job.degree:
            missing.append("missing:degree")
        else:
            job_level = parse_degree(job.degree)
            my_level = parse_degree(rules.my_degree)
            if my_level > 0 and job_level > my_level:
                return (False, f"学历要求过高: {job.degree}", missing)

    # my_experience_years
    if rules.my_experience_years > 0:
        if not job.experience:
            missing.append("missing:experience")
        else:
            required = parse_experience(job.experience)
            if required > rules.my_experience_years:
                return (False, f"经验要求过高: {job.experience}", missing)

    # hr_active_within_days
    if rules.hr_active_within_days > 0:
        if not job.hr_active:
            missing.append("missing:hr_active")
        else:
            days = parse_hr_active(job.hr_active)
            if days is None:
                missing.append("missing:hr_active")
            elif days > rules.hr_active_within_days:
                return (False, f"HR 活跃度不足: {job.hr_active}", missing)

    return (True, "", missing)


def screen(job: Job, rules: RulesConfig) -> ScreenResult:
    """详情级筛选：硬过滤 -> LLM 打分 -> 阈值判定。

    缺失字段放行并在 reasons 中标注 missing:<field>。
    LLM 调用使用 app.llm.client.get_client().chat(json_mode=True)。
    """
    result = ScreenResult()

    passed_hard, fail_reason, missing_notes = _check_detail_hard(job, rules)
    result.reasons.extend(missing_notes)

    if not passed_hard:
        result.passed_hard = False
        result.fail_reason = fail_reason
        result.final = "FAILED"
        return result

    result.passed_hard = True

    # LLM 打分可关闭：关闭则硬过滤通过即投（不调 LLM）
    if not rules.llm_enabled:
        result.score = -1.0   # 哨兵：未打分
        result.final = "CLAIMED"
        result.reasons.append("LLM 打分已关闭：硬过滤通过，直接投递")
        return result

    from app.llm.client import get_client  # 延迟导入避免循环

    profile_section = f"\n候选人画像：{rules.profile}" if rules.profile else ""
    prompt = (
        "你是一位求职助理，请对以下岗位打分（0-100 分），并给出简短理由列表。\n"
        f"职位：{job.title}\n公司：{job.company}\n薪资：{job.salary}\n"
        f"城市：{job.area}\nJD：{job.jd[:500]}{profile_section}\n\n"
        '请以 JSON 格式回答：{"score": <int 0-100>, "reasons": [<str>, ...]}'
    )
    try:
        raw = get_client().chat(
            messages=[{"role": "user", "content": prompt}],
            json_mode=True,
        )
        data = json.loads(raw) if isinstance(raw, str) else raw
        result.score = float(data.get("score", 0))
        result.reasons.extend(data.get("reasons", []))
    except Exception as exc:
        logger.warning("screener LLM 打分失败: %s", exc)
        result.llm_unavailable = True
        result.score = 0.0
        result.reasons.append(f"LLM 调用失败: {type(exc).__name__}: {str(exc)[:80]}")

    # 阈值判定
    if result.llm_unavailable:
        result.final = "FAILED"
        result.fail_reason = "LLM 不可用（如 403 被拒）：检查 GPT_API_KEY/中转，或在规则页关闭 LLM 打分"
    elif result.score >= rules.llm_threshold:
        result.final = "CLAIMED"
    else:
        result.final = "FAILED"
        result.fail_reason = f"评分 {result.score:.0f} < 阈值 {rules.llm_threshold}"

    return result


# ---------------------------------------------------------------------------
# 写库
# ---------------------------------------------------------------------------


def apply_screen_result(
    session: Session, application_id: int, result: ScreenResult
) -> None:
    """将 ScreenResult 落库：Application.status/fail_reason + Job.score/reasons。"""
    app = session.get(Application, application_id)
    if app is None:
        logger.warning("apply_screen_result: Application %d 不存在", application_id)
        return

    app.status = (
        ApplicationStatus.CLAIMED if result.final == "CLAIMED" else ApplicationStatus.FAILED
    )
    app.fail_reason = result.fail_reason
    app.updated_at = datetime.now()
    session.add(app)

    if result.score > 0:
        job = session.get(Job, app.job_id)
        if job is not None:
            job.score = result.score
            job.reasons = json.dumps(result.reasons, ensure_ascii=False)
            job.updated_at = datetime.now()
            session.add(job)

    session.commit()
