"""runner — 唯一设备驱动（slim-v3 §3）。

状态机：IDLE → RUNNING → PAUSED_GEETEST / STOPPED
RUNNING 子态：
  - applying（投递+巡检）：滚动采集→prefilter→[开详情→DUP预检→补全→screen→dispatch_one]
    →回列表，卡间 interval；每 K 卡或超时插一轮巡检。
  - inbox_only（仅巡检）：daily_limit 满或夜停时停投不滚列表，按 inbox_poll 固定轮询，
    每轮循环开头重算（配额跨日归零/夜停结束自动回 applying）。

生命周期（A11）：
  - 单例，持 Task 句柄；start() 幂等——活跃 Task 存在则拒绝（API 返 409，防双驱动）。
  - 两条停止路径收敛：正常 stop（翻 flag→循环退出→await）；geetest 自停
    （显式置 _running=False + PAUSED_GEETEST → 函数返回 → Task done → 下次 run 干净重启）。
  - 不在 lifespan 自动开跑：投递由用户在前端显式启动（半自动边界）。

决策权边界：runner 只编排；"是否投递"由 screener/dispatcher 决定，
设备层只上报观测（observed_label/页面状态）。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time as _time
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.automation import inbox_watcher
from app.config import settings
from app.db import engine
from app.models import Application, ApplicationStatus, Job, RunLog
from app.pipeline import dispatcher
from app.pipeline.collector import collect_jobs
from app.pipeline.rate_limiter import rate_limiter
from app.pipeline.screener import apply_screen_result, prefilter, screen
from app.rules import RulesConfig, load_rules

logger = logging.getLogger(__name__)

INBOX_EVERY_K_CARDS = 5          # 每处理 K 卡插一轮巡检（时间维 OR 兜底见循环）
SCROLL_MISS_LIMIT = 8            # 连续空滚屏次数上限（列表喂尽 → 歇巡检）


def _runlog(event: str, message: str, app_id: Optional[int] = None,
            level: str = "INFO") -> None:
    with Session(engine) as session:
        session.add(RunLog(event=event, message=message,
                           application_id=app_id, level=level))
        session.commit()


def _load_rules() -> RulesConfig:
    with Session(engine) as session:
        return load_rules(session)


class PipelineRunner:
    """进程内单例。控制面（start/stop/status）+ 主循环。"""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.state = "IDLE"          # IDLE | RUNNING | PAUSED_GEETEST | STOPPED
        self.sub_state = ""          # applying | inbox_only
        self.paused_reason = ""
        self.serial = ""
        self.started_at: Optional[str] = None
        self.last_error = ""
        self.stats: dict[str, int] = {}

    # ------------------------------------------------------------------
    # 控制面
    # ------------------------------------------------------------------

    def is_active(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, serial: str) -> bool:
        """幂等启动：已有活跃 Task → False（API 据此返 409，防双驱动）。"""
        if self.is_active():
            return False
        self.serial = serial
        self._running = True
        self.state = "RUNNING"
        self.sub_state = "applying"
        self.paused_reason = ""
        self.last_error = ""
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.stats = {"collected": 0, "prefilter_fail": 0, "screened": 0,
                      "applied": 0, "dup": 0, "failed": 0, "inbox_new": 0}
        self._source = "job_list"  # 采集源：职位列表（推荐）
        self._task = asyncio.create_task(self._run(), name="pipeline-runner")
        return True

    async def stop(self) -> None:
        """请求停止并等 Task 真停（无悬挂，A11）。"""
        self._running = False
        task = self._task
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=180)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                task.cancel()
        if self.state != "PAUSED_GEETEST":
            self.state = "STOPPED"

    async def status(self) -> dict:
        rules = _load_rules()
        quota = await rate_limiter.get_quota(daily_limit=rules.daily_limit)
        return {
            "state": self.state,
            "sub_state": self.sub_state if self.state == "RUNNING" else "",
            "paused_reason": self.paused_reason,
            "serial": self.serial,
            "started_at": self.started_at,
            "last_error": self.last_error,
            "active": self.is_active(),
            "stats": dict(self.stats),
            "today_applied": quota["apply_count"],
            "daily_limit": rules.daily_limit,
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _pause_geetest(self) -> None:
        """geetest 自停：显式复位 flag + 置状态，使下次 /pipeline/run 能干净重启。"""
        self._running = False
        self.state = "PAUSED_GEETEST"
        self.paused_reason = "检测到风控验证页，需人工在真机处理后重新启动"
        _runlog("geetest", self.paused_reason, level="WARNING")

    async def _sleep(self, seconds: float) -> None:
        """可中断 sleep：stop 后最多 1s 内退出。"""
        end = _time.monotonic() + seconds
        while self._running and _time.monotonic() < end:
            await asyncio.sleep(min(1.0, end - _time.monotonic()))

    @staticmethod
    def _fail_app(app_id: int, reason: str, event: str = "prefilter") -> None:
        with Session(engine) as session:
            app = session.get(Application, app_id)
            if app is None:
                return
            app.status = ApplicationStatus.FAILED
            app.fail_reason = reason
            app.updated_at = datetime.now()
            session.add(app)
            job = session.get(Job, app.job_id)
            label = f"{job.company}｜{job.title}" if job else f"#{app_id}"
            session.add(RunLog(event=event, message=f"淘汰 {label}：{reason}",
                               application_id=app_id, level="INFO"))
            session.commit()

    @staticmethod
    def _job_of(app_id: int) -> Optional[Job]:
        with Session(engine) as session:
            app = session.get(Application, app_id)
            if app is None:
                return None
            job = session.get(Job, app.job_id)
            if job is None:
                return None
            return Job.model_validate(job.model_dump())  # detached copy

    @staticmethod
    def _enrich_job(app_id: int, fields: dict[str, str]) -> Optional[Job]:
        """详情字段覆盖列表值（详情更权威），返回 detached Job 供 screen 使用。"""
        with Session(engine) as session:
            app = session.get(Application, app_id)
            if app is None:
                return None
            job = session.get(Job, app.job_id)
            if job is None:
                return None
            if fields.get("jd"):
                job.jd = fields["jd"]
            if fields.get("degree"):
                job.degree = fields["degree"]
            if fields.get("experience"):
                job.experience = fields["experience"]
            if fields.get("location"):
                job.area = fields["location"]
            if fields.get("hr_name"):
                job.hr_name = fields["hr_name"]
            if fields.get("hr_active"):
                job.hr_active = fields["hr_active"]
            job.detail_fetched_at = datetime.now()
            job.updated_at = datetime.now()
            session.add(job)
            session.commit()
            session.refresh(job)
            return Job.model_validate(job.model_dump())

    @staticmethod
    def _screen_and_persist(app_id: int, job: Job, rules: RulesConfig):
        """screen（纯硬过滤，阻塞）+ 落库。在线程池中执行。"""
        result = screen(job, rules)
        with Session(engine) as session:
            apply_screen_result(session, app_id, result)
            session.commit()
        return result

    # ------------------------------------------------------------------
    # 采集源锚点（新职位优先 → 职位列表 fallback）
    # ------------------------------------------------------------------

    async def _ensure_anchor(self, driver) -> bool:
        """确保停在当前采集源锚点页。"""
        if self._source == "new_jobs":
            return await asyncio.to_thread(driver.ensure_on_new_jobs)
        return await asyncio.to_thread(driver.ensure_on_list)

    async def _back_to_anchor(self, driver) -> None:
        """投递/失败后回到当前采集源锚点页（按返回键退栈，保留 feed 不刷新）。"""
        if self._source == "new_jobs":
            await asyncio.to_thread(driver.back_to_new_jobs)
        else:
            await asyncio.to_thread(driver.back_to_list)

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        from app.pages.boss_wxapp import BossWxappDriver as BossDriver  # 延迟导入

        try:
            driver = BossDriver(self.serial)
            await asyncio.to_thread(driver.prepare_device)
        except Exception as e:  # noqa: BLE001
            self._running = False
            self.state = "STOPPED"
            self.last_error = f"设备准备失败: {e}"
            _runlog("runner_error", self.last_error, level="ERROR")
            return

        seen: set[tuple[str, str]] = set()
        cards_since_inbox = 0
        last_inbox_ts = 0.0
        scroll_misses = 0
        _runlog("runner_start", f"runner 启动 serial={self.serial}")

        while self._running:
            try:
                rules = _load_rules()

                # ---- 子态重算（每轮开头：夜停/配额，跨日自动归零）----
                quota = await rate_limiter.get_quota(daily_limit=rules.daily_limit)
                quota_left = rules.daily_limit - quota["apply_count"]
                if dispatcher.is_night_stop(rules) or quota_left <= 0:
                    if self.sub_state != "inbox_only":
                        _runlog("runner_substate",
                                f"进入仅巡检子态（夜停或配额满，今日余 {quota_left}）")
                        self.sub_state = "inbox_only"
                    n = await asyncio.to_thread(inbox_watcher.poll_once, driver)
                    self.stats["inbox_new"] += n
                    last_inbox_ts = _time.monotonic()
                    await self._sleep(random.uniform(
                        settings.inbox_poll_min_sec, settings.inbox_poll_max_sec))
                    continue
                if self.sub_state != "applying":
                    _runlog("runner_substate", "回到投递+巡检子态")
                    self.sub_state = "applying"

                # ---- geetest 检测（采集前）----
                if await asyncio.to_thread(driver.detect_verify):
                    self._pause_geetest()
                    return

                # ---- 锚点自愈：确保在当前采集源锚点页（新职位/职位列表）----
                if not await self._ensure_anchor(driver):
                    _runlog("runner_anchor", "未能回到采集源锚点，跳过本轮重试", level="WARNING")
                    await self._sleep(5)
                    continue

                # ---- 采集当前屏，取第一张未处理卡（抗列表重排）----
                page_cards = await asyncio.to_thread(driver.scrape_page)
                fresh = [c for c in page_cards
                         if (c.raw.company, c.raw.title) not in seen]
                if not fresh:
                    await asyncio.to_thread(driver.scroll_list)
                    scroll_misses += 1
                    if scroll_misses >= SCROLL_MISS_LIMIT:
                        scroll_misses = 0
                        # 职位列表暂投尽：回顶+下拉刷新 + 巡检 + 歇 3 分钟等新岗
                        _runlog("feed_idle", "职位列表暂投尽，回顶+刷新+巡检+歇 3 分钟等新岗")
                        await asyncio.to_thread(driver.refresh_feed)
                        n = await asyncio.to_thread(inbox_watcher.poll_once, driver)
                        self.stats["inbox_new"] += n
                        last_inbox_ts = _time.monotonic()
                        await self._sleep(180)
                    continue
                scroll_misses = 0

                card = fresh[0]
                seen.add((card.raw.company, card.raw.title))
                # ---- 猎头/代招过滤（列表级，HR 职务含关键词，零额外设备动作）----
                if rules.exclude_agency and card.raw.hr_title and any(
                        kw in card.raw.hr_title for kw in (rules.agency_keywords or [])):
                    _runlog("agency_skip",
                            f"跳过猎头/代招 {card.raw.company}｜{card.raw.title}（{card.raw.hr_title}）")
                    self.stats["prefilter_fail"] += 1
                    continue
                app_ids = collect_jobs([card.raw])
                if not app_ids:
                    continue  # jd_hash 已存在（历史已采/已投）
                app_id = app_ids[0]
                self.stats["collected"] += 1

                # ---- 列表级 prefilter（零额外设备动作）----
                job = self._job_of(app_id)
                if job is None:
                    continue
                passed, reason = prefilter(job, rules)
                if not passed:
                    self._fail_app(app_id, reason)
                    self.stats["prefilter_fail"] += 1
                    continue

                # ---- 开详情 ----
                ok = await asyncio.to_thread(
                    driver._tap_until, card.cx, card.cy, "职位详情页")
                if not ok:
                    self._fail_app(app_id, "未进详情页")
                    self.stats["failed"] += 1
                    continue
                detail = await asyncio.to_thread(driver.dump)
                if detail is None:
                    await self._back_to_anchor(driver)
                    self._fail_app(app_id, "详情页 dump 失败")
                    self.stats["failed"] += 1
                    continue

                # ---- DUP 预检（扣配额/写 SENDING 之前；设备只上报 label）----
                label = await asyncio.to_thread(driver.read_chat_button_label, detail)
                if rules.dedup_contacted and "继续沟通" in label:
                    dispatcher.mark_dup(app_id)
                    self.stats["dup"] += 1
                    await self._back_to_anchor(driver)
                    continue

                # ---- 详情补全（详情覆盖列表）----
                fields = await asyncio.to_thread(driver.scrape_detail_fields, detail)
                job = self._enrich_job(app_id, fields) or job

                # ---- 详情级 screen（纯硬过滤）----
                result = await asyncio.to_thread(
                    self._screen_and_persist, app_id, job, rules)
                self.stats["screened"] += 1
                label = f"{job.company}｜{job.title}"
                if result.final != "CLAIMED":
                    _runlog("screen_fail", f"淘汰 {label}：{result.fail_reason}", app_id)
                    await self._back_to_anchor(driver)
                    continue
                _runlog("screen_pass", f"通过 {label}", app_id)

                # ---- 投递（dispatcher 状态机；人已在详情页）----
                outcome = await dispatcher.dispatch_one(app_id, driver, rules)
                if outcome == "SENT":
                    self.stats["applied"] += 1
                elif outcome == "FAILED":
                    self.stats["failed"] += 1
                await self._back_to_anchor(driver)

                # ---- geetest 检测（投后）----
                if await asyncio.to_thread(driver.detect_verify):
                    self._pause_geetest()
                    return

                # ---- 卡间巡检（K 卡 OR 时间兜底）----
                cards_since_inbox += 1
                if (cards_since_inbox >= INBOX_EVERY_K_CARDS
                        or _time.monotonic() - last_inbox_ts > settings.inbox_poll_min_sec):
                    n = await asyncio.to_thread(inbox_watcher.poll_once, driver)
                    self.stats["inbox_new"] += n
                    cards_since_inbox = 0
                    last_inbox_ts = _time.monotonic()

                # ---- 卡间随机间隔（拟人，锁外）----
                await self._sleep(random.uniform(
                    rules.interval_min_sec, rules.interval_max_sec))

            except Exception as e:  # noqa: BLE001
                logger.exception("runner 循环异常")
                self.last_error = str(e)
                _runlog("runner_error", f"循环异常: {e}", level="ERROR")
                await self._sleep(10)

        self.state = "STOPPED"
        _runlog("runner_stop", "runner 已停止")


# 进程内单例（API 与 lifespan 共用）
runner = PipelineRunner()
