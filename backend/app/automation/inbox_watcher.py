"""inbox_watcher — HR 消息巡检（runner 循环内串行调用，无独立 Task/无锁竞争）。

实现（D0 固化的消息页结构）：
  消息 tab → scrape_conversations()（tv_name/tv_position/tv_msg/tv_time_v2/
  iv_msg_status/未读badge）→ 按 position='公司 | 岗位' 匹配 Application →
  新回复落 Message + RunLog(event="inbox_reply"，经 /logs/stream SSE 推前端) →
  回职位 tab。

新回复判定：
  - unread 角标非空 且 status != '[送达]'（'[送达]'=我方最后发言）
  - 排除系统回显文案（撤回提示等）
  - 与该 Application 最新一条 Message 文本相同则去重跳过
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Session, select

from app.db import engine
from app.models import Application, Job, Message, MessageRole, RunLog

if TYPE_CHECKING:
    from app.pages.boss_wxapp import BossWxappDriver as BossDriver

logger = logging.getLogger(__name__)

# 非 HR 实质内容的系统文案（出现即跳过）
_ECHO_MARKS = ("你撤回了", "您正在与", "你正在与")


def _log(session: Session, event: str, message: str,
         app_id: Optional[int] = None) -> None:
    session.add(RunLog(event=event, message=message, application_id=app_id, level="INFO"))


def _match_application(session: Session, position: str) -> Optional[Application]:
    """按会话 position='公司 | 岗位' 匹配最近的 Application（best-effort）。

    消息页公司名可能是 Job.company 的前缀/简称（'上海君兴' vs '上海君兴信息科技'），
    用 LIKE 双向包含；多条命中取最新。未匹配返回 None（调用方记 RunLog）。
    """
    parts = [p.strip() for p in position.split("|")]
    company = parts[0] if parts else ""
    title_kw = parts[1] if len(parts) > 1 else ""
    if not company:
        return None
    rows = session.exec(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)  # type: ignore[arg-type]
        .where(Job.company.contains(company))     # type: ignore[attr-defined]
        .order_by(Application.id.desc())          # type: ignore[attr-defined]
    ).all()
    if not rows:
        return None
    for app, job in rows:
        if not title_kw or title_kw in job.title or job.title in title_kw:
            return app
    return rows[0][0]


def poll_once(driver: "BossDriver") -> int:
    """巡检一轮（同步阻塞，runner 经 asyncio.to_thread 调用）。返回新回复条数。"""
    if not driver.open_message_tab():
        logger.warning("inbox: 消息 tab 未到位，跳过本轮")
        driver.back_to_job_tab()
        return 0
    try:
        convs = driver.scrape_conversations()
    finally:
        # 无论解析成败都回职位 tab（runner 锚点）
        driver.back_to_job_tab()

    new_count = 0
    with Session(engine) as session:
        for c in convs:
            is_hr_new = bool(c.get("unread")) and c.get("status") != "[送达]"
            if not is_hr_new:
                continue
            last_msg = c.get("last_msg", "")
            if not last_msg or any(m in last_msg for m in _ECHO_MARKS):
                continue
            app = _match_application(session, c.get("position", ""))
            if app is None:
                _log(session, "inbox_unmatched",
                     f"未匹配会话: {c.get('hr_name')}（{c.get('position')}）: {last_msg[:50]}")
                continue
            # 去重：该投递记录最新一条相同文本不重复落
            latest = session.exec(
                select(Message)
                .where(Message.application_id == app.id)
                .order_by(Message.id.desc())  # type: ignore[attr-defined]
                .limit(1)
            ).first()
            if latest is not None and latest.text == last_msg:
                continue
            session.add(Message(
                application_id=app.id, role=MessageRole.HR, text=last_msg,
            ))
            app.last_poll_at = datetime.now()
            app.taken_over = False   # 新回复 → 待人工处理（真机回复后前端标记）
            session.add(app)
            _log(session, "inbox_reply",
                 f"HR 新回复: {c.get('hr_name')}（{c.get('position')}）: {last_msg[:60]}",
                 app.id)
            new_count += 1
        session.commit()
    return new_count
