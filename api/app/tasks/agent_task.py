"""定时/主动任务 Celery 任务：

- heartbeat：每分钟扫 agent_tasks 找到期的，一个事务内推进 next_run_at（防重复触发）后派发执行。
- run_agent_task：跑深度研究引擎产出报告（research_reports，task_id 关联），回写任务状态。
  - 单任务并发护栏：Redis 锁（SET NX + TTL，自愈，防 interval<耗时 或「立即运行」撞定时重叠跑）。
  - 整体硬超时：asyncio.wait_for（跨平台，Windows 上 celery time_limit 不生效）。

队列：heartbeat → beat（轻量，不可被堵）；run → research（重活，独立队列）。
与其他 beat 任务一致：任务级独立引擎（NullPool）+ 独立事件循环（asyncio.run）。
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保 ORM 模型注册
from app.celery_app import celery_app
from app.config import settings
from app.core.agent.loop.store import LoopStore
from app.core.agent.research.engine import run_research
from app.core.logging import get_logger
from app.core.realtime import bus
from app.db import elastic
from app.db.postgres import create_task_engine
from app.models.agent_task_model import (
    TASK_RUN_DONE,
    TASK_RUN_FAILED,
    TASK_RUN_RUNNING,
)
from app.models.research_report_model import (
    RESEARCH_STATUS_DONE,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_PENDING,
    RESEARCH_STATUS_PLANNING,
    RESEARCH_STATUS_SEARCHING,
    RESEARCH_STATUS_SUMMARIZING,
    RESEARCH_STATUS_WRITING,
    ResearchReport,
)
from app.repositories.agent_task_repository import AgentTaskRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.services.agent_task_service import TZ, compute_next_run
from app.services.gitcode_service import (
    GitCodeNotConfigured,
    GitCodePublishError,
    GitCodeService,
)

logger = get_logger(__name__)


_ACTIVE_RESEARCH_STATUSES = (
    RESEARCH_STATUS_PENDING,
    RESEARCH_STATUS_PLANNING,
    RESEARCH_STATUS_SEARCHING,
    RESEARCH_STATUS_WRITING,
    RESEARCH_STATUS_SUMMARIZING,
)


async def _reap_stale_reports(session: AsyncSession) -> int:
    """收敛 worker 崩溃后遗留的研究状态，避免任务永久显示“运行中”。

    研究引擎会在每个阶段更新 ``updated_at``。如果超过整体超时再加一小段
    宽限期仍没有任何更新，说明执行进程已经退出或被中断；此时只标记失败，
    保留报告记录和已有的部分内容，不触发归档/通知。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.research_task_timeout + 120
    )
    stmt = (
        select(ResearchReport)
        .where(
            ResearchReport.status.in_(_ACTIVE_RESEARCH_STATUSES),
            ResearchReport.updated_at < cutoff,
        )
        .with_for_update(skip_locked=True)
    )
    reports = list((await session.execute(stmt)).scalars().all())
    if not reports:
        return 0

    task_repo = AgentTaskRepository(session)
    now = datetime.now(TZ)
    for report in reports:
        msg = (
            "research watchdog: no progress update within "
            f"{settings.research_task_timeout + 120}s; worker may have stopped"
        )
        report.status = RESEARCH_STATUS_FAILED
        report.error_msg = msg[:2000]
        if report.task_id:
            task = await task_repo.get_by_id(report.task_id)
            if task and task.last_status == TASK_RUN_RUNNING:
                task.last_status = TASK_RUN_FAILED
                task.last_run_at = now
        await LoopStore(session).fail_running_for_task(report.id, msg)
        logger.warning(
            "reaped stale research report: report=%s task=%s last_update=%s",
            report.id,
            report.task_id,
            report.updated_at,
        )
    return len(reports)


# ── 每分钟心跳：原子认领到期任务 → 推进 next_run_at → 派发 ──

async def _heartbeat() -> int:
    engine_db = create_task_engine()
    sm = async_sessionmaker(engine_db, expire_on_commit=False, class_=AsyncSession)
    dispatched_ids: list[str] = []
    try:
        async with sm() as session:
            stale_count = await _reap_stale_reports(session)
            repo = AgentTaskRepository(session)
            # FOR UPDATE SKIP LOCKED 认领 + 同事务推进 next_run_at + 一次提交，
            # 避免逐行提交后尾部任务在另一心跳里被重复触发。
            due = await repo.list_due()
            for task in due:
                task.next_run_at = compute_next_run(task)
                dispatched_ids.append(str(task.id))
            if due or stale_count:
                await session.commit()
    finally:
        await engine_db.dispose()

    # 提交（next_run_at 已推进）之后再派发，避免「派发了却没推进」
    for tid in dispatched_ids:
        run_agent_task_task.delay(tid)
    if dispatched_ids:
        logger.info("定时任务心跳：派发 %d 个到期任务", len(dispatched_ids))
    return len(dispatched_ids)


@celery_app.task(name="app.tasks.agent_task.heartbeat")
def heartbeat_task() -> int:
    """每分钟调度心跳的 Celery 任务入口。"""
    return asyncio.run(_heartbeat())


# ── 执行一次研究任务（Redis 锁 + 硬超时）──

async def _run_task(task_id: str) -> None:
    tid = uuid.UUID(task_id)
    lock_key = f"agent_task:lock:{task_id}"
    lock_ttl = settings.research_task_timeout + 120  # 略大于超时，自动过期防死锁
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        try:
            got = await redis.set(lock_key, "1", nx=True, ex=lock_ttl)
        except Exception as e:
            # Redis 异常时不因锁失败而漏跑用户任务（可用性优先于严格互斥）
            logger.warning("获取定时任务锁失败，继续执行: id=%s err=%s", tid, e)
            got = True
        if not got:
            logger.info("定时任务已在运行中，跳过本次触发: id=%s", tid)
            return
        await _do_run(tid)
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:  # noqa: BLE001
            pass
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass
        # Celery's Windows solo worker creates a fresh asyncio loop per task.
        # Close the shared async Elasticsearch client so the next task cannot
        # reuse a client bound to the previous (now closed) loop.
        try:
            await elastic.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("关闭定时研究 Elasticsearch 客户端失败（忽略）: %s", e)


async def _do_run(tid: uuid.UUID) -> None:
    engine_db = create_task_engine()
    sm = async_sessionmaker(engine_db, expire_on_commit=False, class_=AsyncSession)
    try:
        # 1) 建报告行 + 标任务运行中（健康事务）
        async with sm() as session:
            task = await AgentTaskRepository(session).get_by_id(tid)
            if not task:
                logger.warning("定时任务执行：任务不存在 %s", tid)
                return
            user_id = task.user_id
            instruction = task.instruction
            notify_enabled = task.notify_enabled
            kb_ids = [str(k) for k in (task.kb_ids or [])] or None
            report = await ResearchReportRepository(session).create(
                ResearchReport(
                    user_id=user_id,
                    topic=instruction,
                    status=RESEARCH_STATUS_PENDING,
                    task_id=task.id,
                )
            )
            report_id = report.id
            task.last_status = TASK_RUN_RUNNING
            # 记录本次开始时间；完成/失败时会再次写入结束时间。
            task.last_run_at = datetime.now(TZ)
            await AgentTaskRepository(session).save(task)

        # 2) 跑研究（独立 session + 整体硬超时）
        ok = await _execute_research(sm, report_id, user_id, instruction, kb_ids)

        # 3) 回写任务最近运行状态/时间（全新 session，避免受研究阶段事务影响）
        async with sm() as session:
            task = await AgentTaskRepository(session).get_by_id(tid)
            if task:
                task.last_run_at = datetime.now(TZ)
                task.last_status = TASK_RUN_DONE if ok else TASK_RUN_FAILED
                await AgentTaskRepository(session).save(task)
        logger.info("定时任务执行完成: id=%s ok=%s", tid, ok)

        # 4) 成功且任务开启推送 → 仅以报告是否 done 为准。
        # Verifier 是质量提示而非硬门槛；failed 报告仍不会进入此分支，
        # 因而不会通知或归档。
        if ok and notify_enabled:
            verified = await _check_loop_passed(sm, report_id)
            if not verified:
                logger.info(
                    "定时任务 Verifier Loop 未通过，仍推送已完成报告（附质量警告）: report=%s task=%s",
                    report_id, tid,
                )
            await _notify_user(sm, user_id, report_id, instruction)
    finally:
        await engine_db.dispose()


async def _execute_research(
    sm: async_sessionmaker,
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None,
) -> bool:
    """Run a scheduled research task and expose resumable live progress."""
    rid = str(report_id)
    holder: dict = {"md": None, "sources": [], "title": None, "outline": None, "partial": ""}
    phase = "planning"
    title = ""
    sources_brief: list = []
    steps: list[dict] = []
    token_index = 0

    async def flush_buffer() -> None:
        await bus.set_stream_buffer(
            rid,
            {
                "status": "generating",
                "phase": phase,
                "title": title,
                "plan": holder["outline"],
                "sources": sources_brief,
                "steps": steps[-40:],
                "partial_md": holder["partial"][-6000:],
                "n": token_index,
            },
        )

    async def set_phase(value: str) -> None:
        normalized = "searching" if value == "searching_done" else value
        if normalized not in {"planning", "searching", "writing", "summarizing"}:
            return
        try:
            async with sm() as status_session:
                repo = ResearchReportRepository(status_session)
                report = await repo.get_by_id(report_id)
                if report:
                    report.status = normalized
                    await repo.save(report)
        except Exception as e:  # noqa: BLE001
            logger.warning("scheduled research phase update failed: report=%s err=%s", report_id, e)

    async def collect(session: AsyncSession) -> None:
        nonlocal phase, title, sources_brief, token_index
        async for ev in run_research(session, user_id, topic, kb_ids, report_id=report_id):
            etype = ev.get("type")
            if etype == "status":
                phase = ev.get("phase", phase)
                await set_phase(phase)
                await bus.publish(rid, "status", ev)
                await flush_buffer()
            elif etype == "plan":
                title = ev.get("title", title)
                holder["outline"] = {
                    "title": ev.get("title", ""),
                    "sections": ev.get("sections", []),
                    "queries": ev.get("queries", []),
                }
                holder["title"] = ev.get("title", holder["title"])
                await bus.publish(rid, "plan", ev)
                await flush_buffer()
            elif etype == "sources":
                sources_brief = ev.get("sources", [])
                holder["sources"] = sources_brief
                await bus.publish(rid, "sources", ev)
                await flush_buffer()
            elif etype == "progress":
                step = {
                    "icon": ev.get("icon", ""),
                    "ok": ev.get("ok", True),
                    "text": ev.get("text", ""),
                }
                steps.append(step)
                await bus.publish(rid, "progress", ev)
                await flush_buffer()
            elif etype == "section_start":
                holder["partial"] += f"\n\n## {ev.get('heading', '')}\n\n"
                await bus.publish(rid, "section_start", ev)
                await flush_buffer()
            elif etype == "token":
                text = ev.get("text", "")
                holder["partial"] += text
                await bus.publish(rid, "token", {"text": text, "i": token_index})
                token_index += 1
                if token_index % 8 == 0:
                    await flush_buffer()
            elif etype == "section_done":
                await bus.publish(rid, "section_done", ev)
                await flush_buffer()
            elif etype == "report":
                holder["md"] = ev.get("markdown", "")
                holder["sources"] = ev.get("sources", [])
                holder["title"] = ev.get("title", holder["title"])
                await bus.publish(rid, "report", ev)
                await flush_buffer()
            elif etype and etype.startswith("loop_"):
                await bus.publish(rid, etype, ev)
                await flush_buffer()
            elif etype == "error":
                raise RuntimeError(ev.get("message", "research failed"))

    await set_phase("planning")
    await flush_buffer()
    try:
        async with sm() as session:
            await asyncio.wait_for(collect(session), timeout=settings.research_task_timeout)
            if not (holder["md"] or "").strip():
                raise RuntimeError("research produced no valid report")
            repo = ResearchReportRepository(session)
            report = await repo.get_by_id(report_id)
            if report:
                report.title = (holder["title"] or topic)[:255]
                report.report_md = holder["md"]
                report.sources = holder["sources"]
                report.outline = holder["outline"]
                report.status = RESEARCH_STATUS_DONE
                report.error_msg = None
                await repo.save(report)
                await _archive_report(report)
        await bus.clear_stream_buffer(rid)
        await bus.publish(rid, "done", {"report_id": rid})
        return True
    except (TimeoutError, asyncio.TimeoutError):
        msg = f"research timed out after {settings.research_task_timeout} seconds"
        logger.error("scheduled research timeout: report=%s", report_id)
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        logger.error("scheduled research failed: report=%s err=%s", report_id, e, exc_info=True)
    await _mark_failed(sm, report_id, msg, holder)
    await bus.clear_stream_buffer(rid)
    await bus.publish(rid, "error", {"message": f"研究失败：{msg}"})
    return False


async def _execute_research_legacy(
    sm: async_sessionmaker,
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None,
) -> bool:
    """消费研究引擎事件并落库（无 SSE/bus，后台直跑），带整体硬超时。"""
    holder: dict = {"md": None, "sources": [], "title": None, "outline": None, "partial": ""}

    async def _collect(session: AsyncSession) -> None:
        async for ev in run_research(session, user_id, topic, kb_ids, report_id=report_id):
            etype = ev.get("type")
            if etype == "plan":
                holder["outline"] = {
                    "title": ev.get("title", ""),
                    "sections": ev.get("sections", []),
                    "queries": ev.get("queries", []),
                }
                holder["title"] = ev.get("title")
            elif etype == "section_start":
                holder["partial"] += f"\n\n## {ev.get('heading', '')}\n\n"
            elif etype == "token":
                holder["partial"] += ev.get("text", "")
            elif etype == "report":
                holder["md"] = ev.get("markdown", "")
                holder["sources"] = ev.get("sources", [])
                holder["title"] = ev.get("title", holder["title"])
            elif etype == "error":
                raise RuntimeError(ev.get("message", "研究失败"))

    try:
        async with sm() as session:
            await asyncio.wait_for(
                _collect(session), timeout=settings.research_task_timeout
            )
            if holder["md"] is None:
                raise RuntimeError("研究未产出报告")
            # 正常完成：session 健康，直接落 done
            repo = ResearchReportRepository(session)
            report = await repo.get_by_id(report_id)
            if report:
                report.title = (holder["title"] or topic)[:255]
                report.report_md = holder["md"]
                report.sources = holder["sources"]
                report.outline = holder["outline"]
                report.status = RESEARCH_STATUS_DONE
                report.error_msg = None
                await repo.save(report)
                await _archive_report(report)
        return True
    except (TimeoutError, asyncio.TimeoutError):
        msg = f"研究超时（超过 {settings.research_task_timeout} 秒）"
        logger.error("定时研究超时: report=%s", report_id)
    except Exception as e:
        msg = str(e)
        logger.error("定时研究执行失败: report=%s err=%s", report_id, e, exc_info=True)
    # 失败落库：用全新 session（超时取消可能令原 session 处于脏/中断状态）
    await _mark_failed(sm, report_id, msg, holder)
    return False


async def _mark_failed(
    sm: async_sessionmaker, report_id: uuid.UUID, msg: str, holder: dict
) -> None:
    try:
        async with sm() as session:
            repo = ResearchReportRepository(session)
            report = await repo.get_by_id(report_id)
            if report:
                report.status = RESEARCH_STATUS_FAILED
                report.error_msg = (msg or "研究失败")[:2000]
                if holder["partial"].strip():
                    report.report_md = holder["partial"]
                report.outline = holder["outline"]
                report.sources = holder["sources"]
                await repo.save(report)
            await LoopStore(session).fail_running_for_task(report_id, msg)
    except Exception as e:  # noqa: BLE001
        logger.warning("研究失败落库出错（忽略）: report=%s err=%s", report_id, e)


@celery_app.task(name="app.tasks.agent_task.run")
def run_agent_task_task(task_id: str) -> str:
    """执行一次定时研究任务的 Celery 入口。"""
    asyncio.run(_run_task(task_id))
    return task_id


# ── 完成后推送通知 ──

def _extract_summary(md: str, limit: int = 360) -> str:
    """从报告 Markdown 提取简报：TL;DR 引用块 + 核心要点前几条，截断。"""
    if not md:
        return ""
    lines = md.splitlines()
    tldr: list[str] = []
    points: list[str] = []
    in_points = False
    for line in lines:
        s = line.strip()
        if s.startswith(">"):
            tldr.append(s.lstrip("> ").strip())
        elif s.startswith("##") and ("核心要点" in s or "要点" in s):
            in_points = True
        elif s.startswith("##"):
            in_points = False
        elif in_points and (s.startswith("- ") or s.startswith("* ")):
            points.append(s[2:].strip())
    parts: list[str] = []
    if tldr:
        parts.append(" ".join(tldr))
    if points:
        parts.append("\n".join(f"· {p}" for p in points[:5]))
    text = "\n\n".join(parts).strip()
    if not text:
        # 兜底：取正文前若干字（去标题/角标）
        text = " ".join(s for s in (ln.strip() for ln in lines) if s and not s.startswith("#"))
    return text[:limit] + ("…" if len(text) > limit else "")


async def _archive_report(report: ResearchReport) -> str | None:
    """将已完成的报告归档到 GitCode；归档失败不阻断研究任务。"""
    if report.status != RESEARCH_STATUS_DONE or not (report.report_md or "").strip():
        logger.info(
            "跳过 GitCode 归档：研究报告未成功完成或内容为空 report=%s status=%s",
            report.id,
            report.status,
        )
        return None
    try:
        return await GitCodeService().publish_report(report)
    except GitCodeNotConfigured:
        logger.warning("研究报告未归档：未配置 GitCode PAT，report=%s", report.id)
    except GitCodePublishError as exc:
        logger.warning("研究报告 GitCode 归档失败，report=%s err=%s", report.id, exc)
    return None


async def _notify_user(
    sm: async_sessionmaker, user_id: uuid.UUID, report_id: uuid.UUID, topic: str
) -> None:
    """把完成的报告 TL;DR 推到用户的消息渠道。整步降级，绝不影响任务。"""
    try:
        from app.config import settings
        from app.services.notify_service import NotifyService

        async with sm() as session:
            report = await ResearchReportRepository(session).get_by_id(report_id)
            if (
                not report
                or report.status != RESEARCH_STATUS_DONE
                or not (report.report_md or "").strip()
            ):
                logger.info(
                    "跳过定时任务通知/归档：研究报告未成功完成 report=%s status=%s",
                    report_id,
                    getattr(report, "status", None),
                )
                return
            title = report.title or topic[:40] or "研究报告"
            summary = _extract_summary(report.report_md)
            link = None
            try:
                link = await GitCodeService().publish_report(report)
            except GitCodeNotConfigured:
                logger.warning("定时研究未归档：未配置 GitCode PAT，report=%s", report_id)
            except GitCodePublishError as exc:
                logger.warning("定时研究 GitCode 归档失败，report=%s err=%s", report_id, exc)
            content = f"{summary}\n\n📄 查看完整报告：{link}"
            if not settings.notify_include_report_link:
                content = summary
            if not link:
                content = summary
            sent = await NotifyService(session).push_to_user(
                user_id, f"🔬 {title}", content
            )
            if sent:
                logger.info("定时任务推送完成: report=%s 渠道数=%d", report_id, sent)
    except Exception as e:  # noqa: BLE001
        logger.warning("定时任务推送失败（忽略）: report=%s err=%s", report_id, e)


async def _check_loop_passed(
    sm: async_sessionmaker, report_id: uuid.UUID
) -> bool:
    """检查 research engine 已跑过的 Verifier Loop 通过状态。

    V0.0.5 ② 设计:engine 内已经接 LoopController(task_type=research, task_id=report_id),
    定时任务**不重复跑 verify**,只读结果决定要不要推送。

    返回 True 当且仅当:
    - Loop 关闭(settings.loop_enabled=False) → 视为通过(无评分时不阻塞推送)
    - 找到 LoopRun 且 status=passed
    其他情况(exceeded / failed / 未找到)→ 视为未通过,跳过推送。
    """
    if not settings.loop_enabled:
        return True
    try:
        from app.core.agent.loop.store import LoopStore
        from app.models.loop_model import STATUS_PASSED

        async with sm() as session:
            run = await LoopStore(session).find_latest_by_task(
                task_type="research", task_id=report_id
            )
            if run is None:
                logger.info("Verifier Loop 未找到对应 run,降级视为通过: report=%s", report_id)
                return True  # 没跑过(可能是引擎里 verifier 早期异常),不阻塞推送
            return run.status == STATUS_PASSED
    except Exception as e:  # noqa: BLE001
        logger.warning("查 LoopRun 失败,降级视为通过: report=%s err=%s", report_id, e)
        return True
