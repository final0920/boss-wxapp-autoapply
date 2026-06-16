"""
rules.py — RulesConfig: 前后端唯一契约（§5.1）。

DB Config(key="rules") 为运行期单一真值源。
load_rules / save_rules 封装读写，损坏/缺失时回退 pydantic 默认值。
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from app.models import Config

logger = logging.getLogger(__name__)


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ---- 列表级硬过滤 ----
    salary_min_k: float = 0          # 期望薪资下限(K)。0=不限。判据: 区间相交
    salary_max_k: float = 0          # 期望薪资上限(K)。0=不限
    salary_floor_k: float = 0        # 起步薪资下限(K)：岗位薪资**下界** < 此值则滤掉(如12→10-15K 下界10<12 被滤)。0=不限；面议(解析失败)不滤
    allowed_cities: list[str] = []   # 空=不限；包含匹配 Job.area
    blocked_areas: list[str] = []    # 区域黑名单，包含匹配
    include_keywords: list[str] = [] # 空=不限；列表级对 title，详情级对 title+jd，含其一即过
    exclude_keywords: list[str] = [] # 命中即滤；作用域 title+company+jd（公司黑名单并入此项）

    # ---- 详情级硬过滤（字段缺失/None → 放行并在 reasons 标注 missing:<field>）----
    company_scales: list[str] = []   # 允许的规模桶，空=不限
    my_degree: str = ""              # 我的学历。岗位要求 > 我 → 滤。空=不限
    my_experience_years: int = 0     # 我的年限。岗位要求下限 > 我 → 滤。0=不限
    hr_active_within_days: int = 0   # HR 活跃天数门槛。0=不限
    dedup_contacted: bool = True     # 设备级"继续沟通"跳过(→DUP) + jd_hash 去重
    exclude_agency: bool = False     # 跳过猎头/代招岗位（按卡片 HR 职务关键词判定，列表级）
    agency_keywords: list[str] = ["猎头", "代招", "招聘代理", "人才经纪"]  # HR 职务含其一 → 视为猎头/代招

    # ---- 投递节奏 ----
    daily_limit: int = 100
    interval_min_sec: int = 20
    interval_max_sec: int = 90
    night_stop_start: str = "23:00"
    night_stop_end: str = "07:00"


_RULES_KEY = "rules"


def load_rules(session: Session) -> RulesConfig:
    """从 DB Config(key="rules") 加载 RulesConfig；缺失或损坏时回退默认值。"""
    row = session.exec(select(Config).where(Config.key == _RULES_KEY)).first()
    if row is None or not row.value:
        return RulesConfig()
    try:
        data = json.loads(row.value)
        # extra="forbid" 会拒绝未知字段；用 model_validate 而非 parse_raw
        # 对旧数据宽容：先用 ignore 模式解析，再重新序列化为严格对象
        return RulesConfig.model_validate(data)
    except Exception as exc:
        logger.warning("rules.load_rules: 解析失败，回退默认值。原因: %s", exc)
        return RulesConfig()


def save_rules(session: Session, rules: RulesConfig) -> None:
    """将 RulesConfig 全量 JSON 写入 DB Config(key="rules")。"""
    from datetime import datetime

    value = rules.model_dump_json()
    row = session.exec(select(Config).where(Config.key == _RULES_KEY)).first()
    if row is None:
        row = Config(key=_RULES_KEY, value=value, updated_at=datetime.now())
        session.add(row)
    else:
        row.value = value
        row.updated_at = datetime.now()
        session.add(row)
    session.commit()
