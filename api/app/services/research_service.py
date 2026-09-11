"""深度研究业务服务：SSE 流式研究（后台生成解耦 + 断线续传）+ 报告管理 + 存知识库。

与单聊一致：生成动作跑在独立 session 的后台任务里，事件经 Redis bus 广播；
本 SSE 连接只订阅转发。客户端断开不影响研究跑完、落库；生成中重连可续传。
"""
import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent.loop.store import LoopStore
from app.core.agent.research.engine import run_research
from app.core.agent.tracing.error_policy import is_non_fatal_loop_failure
from app.core.exceptions import BizError
from app.core.llm.chat_model import get_default_chat_config
from app.core.logging import get_logger
from app.core.realtime import bus
from app.db.postgres import SessionLocal
from app.models.notify_channel_model import CHANNEL_FEISHU
from app.models.research_report_model import (
    RESEARCH_STATUS_DONE,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_PENDING,
    ResearchReport,
)
from app.repositories.research_report_repository import ResearchReportRepository
from app.schemas.research_schema import ResearchStartRequest
from app.services.gitcode_service import (
    GitCodeNotConfigured,
    GitCodePublishError,
    GitCodeService,
)
from app.services.notify_service import NotifyService

logger = get_logger(__name__)

# 后台任务引用集合（防 create_task 被 GC 回收）
_BG_TASKS: set = set()
_BUFFER_FLUSH_EVERY = 8


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ResearchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ResearchReportRepository(session)

    # ── 发起 + 流式 ──

    async def stream_research(
        self, user_id: uuid.UUID, body: ResearchStartRequest
    ) -> AsyncGenerator[str, None]:
        """发起一次研究并流式推进度：建报告行 → 触发后台生成 → 订阅转发。"""
        topic = body.topic.strip()
        if not topic:
            yield _sse("error", {"message": "研究主题不能为空"})
            return

        # 前置校验（失败立即返回，不建任务）：需配对话模型 + 联网搜索模型
        try:
            await get_default_chat_config(self.session, user_id)
            await self._require_websearch(user_id)
        except BizError as e:
            yield _sse("error", {"message": e.message})
            return

        # 建报告行（独立 session 用完即关）
        try:
            async with SessionLocal() as session:
                report = await ResearchReportRepository(session).create(
                    ResearchReport(
                        user_id=user_id,
                        topic=topic,
                        status=RESEARCH_STATUS_PENDING,
                    )
                )
                rid = str(report.id)
        except Exception as e:
            yield _sse("error", {"message": f"创建研究失败：{e}"})
            return

        yield _sse("meta", {"report_id": rid, "topic": topic})

        pubsub = await bus.open_channel(rid)
        try:
            lock_owner = await bus.acquire_turn_lock(rid)
            if lock_owner:
                task = asyncio.create_task(
                    self._run_research_bg(user_id, uuid.UUID(rid), body, lock_owner)
                )
                _BG_TASKS.add(task)
                task.add_done_callback(_BG_TASKS.discard)
            async for sse in self._relay(pubsub, rid):
                yield sse
        finally:
            await bus.close_channel(pubsub, rid)

    async def resume_events(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> AsyncGenerator[str, None]:
        """重连续传：生成中 → 补推快照 + 续接 token；已结束 → 直接回放最终报告。"""
        async with SessionLocal() as session:
            report = await ResearchReportRepository(session).get(user_id, report_id)
        if not report:
            yield _sse("error", {"message": "研究报告不存在"})
            return
        rid = str(report_id)
        buf = await bus.get_stream_buffer(rid)
        # Scheduled/Celery research creates the report before its worker starts.
        # Give that worker a short grace period to publish the initial snapshot
        # instead of returning `idle` during this startup race.
        running_statuses = {
            RESEARCH_STATUS_PENDING,
            "planning",
            "searching",
            "writing",
            "summarizing",
        }
        if not (buf and buf.get("status") == "generating") and report.status in running_statuses:
            for _ in range(20):
                await asyncio.sleep(0.5)
                buf = await bus.get_stream_buffer(rid)
                async with SessionLocal() as session:
                    refreshed = await ResearchReportRepository(session).get(user_id, report_id)
                if refreshed:
                    report = refreshed
                if (buf and buf.get("status") == "generating") or report.status not in running_statuses:
                    break
        if not (buf and buf.get("status") == "generating"):
            # 已结束：回放最终报告
            if report.status == RESEARCH_STATUS_DONE and report.report_md:
                yield _sse(
                    "report",
                    {
                        "title": report.title or report.topic,
                        "markdown": report.report_md,
                        "sources": report.sources or [],
                    },
                )
                yield _sse("done", {"report_id": rid})
            elif report.status == RESEARCH_STATUS_FAILED:
                yield _sse("error", {"message": report.error_msg or "研究失败"})
            else:
                yield _sse("idle", {})
            return

        pubsub = await bus.open_channel(rid)
        try:
            buf2 = await bus.get_stream_buffer(rid)
            if not (buf2 and buf2.get("status") == "generating"):
                # The worker may have finished between the first snapshot and
                # opening Pub/Sub. Re-read the report before declaring idle.
                async with SessionLocal() as session:
                    latest = await ResearchReportRepository(session).get(user_id, report_id)
                if latest and latest.status == RESEARCH_STATUS_DONE and latest.report_md:
                    yield _sse(
                        "report",
                        {
                            "title": latest.title or latest.topic,
                            "markdown": latest.report_md,
                            "sources": latest.sources or [],
                        },
                    )
                    yield _sse("done", {"report_id": rid})
                elif latest and latest.status == RESEARCH_STATUS_FAILED:
                    yield _sse("error", {"message": latest.error_msg or "研究失败"})
                else:
                    yield _sse("idle", {})
                return
            buf = buf2
            seen = int(buf.get("n", 0))
            yield _sse(
                "resume",
                {
                    "phase": buf.get("phase", ""),
                    "title": buf.get("title", ""),
                    "plan": buf.get("plan"),
                    "sources": buf.get("sources", []),
                    "steps": buf.get("steps", []),
                    "partial_md": buf.get("partial_md", ""),
                },
            )
            async for sse in self._relay(pubsub, rid, skip_token_before=seen):
                yield sse
        finally:
            await bus.close_channel(pubsub, rid)

    async def _relay(
        self, pubsub, rid: str, skip_token_before: int = 0
    ) -> AsyncGenerator[str, None]:
        """把频道事件转成 SSE 转发，遇 done/error 结束。"""
        async for evt in bus.iter_channel(pubsub, rid):
            ev = evt.get("event")
            data = evt.get("data") or {}
            if ev == "_ping":
                yield ": ping\n\n"
            elif ev == "token":
                if int(data.get("i", 0)) < skip_token_before:
                    continue
                yield _sse("token", {"text": data.get("text", "")})
            elif ev in {
                "status",
                "plan",
                "sources",
                "progress",
                "section_start",
                "section_done",
                "report",
            }:
                yield _sse(ev, data)
            elif ev and ev.startswith("loop_"):
                # V0.0.5 ② Verifier Loop 事件直通(loop_started / loop_verify_start /
                # loop_verify_done / loop_repair_start / loop_repair_done / loop_finished)
                yield _sse(ev, data)
            elif ev == "done":
                yield _sse("done", data)
                return
            elif ev == "error":
                yield _sse("error", data)
                return

    async def _run_research_bg(
        self, user_id: uuid.UUID, report_id: uuid.UUID, body: ResearchStartRequest,
        lock_owner: str,
    ) -> None:
        """Run manual research with the same whole-task deadline as scheduled runs.

        The previous implementation only timed out individual model/fetch calls.
        A stuck stream, database operation, or third-party client could therefore
        leave a report running forever.  Keep the implementation in a separate
        coroutine so ``wait_for`` can cancel the complete task reliably.
        """
        try:
            await asyncio.wait_for(
                self._run_research_bg_impl(user_id, report_id, body, lock_owner),
                timeout=settings.research_task_timeout,
            )
        except asyncio.TimeoutError:
            message = f"研究超时（超过 {settings.research_task_timeout} 秒）"
            logger.error("研究后台任务超时: report=%s", report_id)
            snapshot = await bus.get_stream_buffer(str(report_id))
            await self._fail(
                report_id,
                message,
                (snapshot or {}).get("partial_md", ""),
                (snapshot or {}).get("plan"),
                (snapshot or {}).get("sources", []),
            )
            await bus.publish(str(report_id), "error", {"message": message})

    async def _run_research_bg_impl(
        self, user_id: uuid.UUID, report_id: uuid.UUID, body: ResearchStartRequest,
        lock_owner: str,
    ) -> None:
        """后台研究任务：独立 session 跑引擎，广播事件 + 写续传缓冲，结束落库。"""
        rid = str(report_id)
        n = 0  # 全局 token 序号（跨章节，用于续传去重）
        partial_md = ""  # 已产出的正文累积（续传快照用）
        phase = "planning"
        title = ""
        plan_snapshot: dict | None = None
        sources_brief: list = []
        steps: list[dict] = []  # 活动流（搜索/抓取/命中/调用工具），续传补推
        final_md: str | None = None
        final_sources: list = []
        final_title: str | None = None

        async def _flush(status: str = "generating") -> None:
            await bus.set_stream_buffer(
                rid,
                {
                    "status": status,
                    "phase": phase,
                    "title": title,
                    "plan": plan_snapshot,
                    "sources": sources_brief,
                    "steps": steps[-40:],
                    "partial_md": partial_md[-6000:],
                    "n": n,
                },
            )

        try:
            kb_ids = await self._resolve_kb_ids(user_id, body.kb_ids)
            async with SessionLocal() as session:
                await self._set_status(session, report_id, "planning")
                await _flush("generating")
                async for ev in run_research(
                    session, user_id, body.topic.strip(), kb_ids, report_id=report_id
                ):
                    etype = ev.get("type")
                    if etype == "status":
                        phase = ev.get("phase", phase)
                        await bus.publish(rid, "status", ev)
                        await self._set_status_safe(report_id, phase)
                        await _flush("generating")
                    elif etype == "plan":
                        title = ev.get("title", "")
                        plan_snapshot = {
                            "title": title,
                            "sections": ev.get("sections", []),
                            "queries": ev.get("queries", []),
                        }
                        await bus.publish(rid, "plan", ev)
                        await _flush("generating")
                    elif etype == "sources":
                        sources_brief = ev.get("sources", [])
                        await bus.publish(rid, "sources", ev)
                        await _flush("generating")
                    elif etype == "progress":
                        steps.append(
                            {
                                "icon": ev.get("icon", ""),
                                "ok": ev.get("ok", True),
                                "text": ev.get("text", ""),
                            }
                        )
                        await bus.publish(rid, "progress", ev)
                    elif etype == "section_start":
                        partial_md += f"\n\n## {ev.get('heading', '')}\n\n"
                        await bus.publish(rid, "section_start", ev)
                    elif etype == "token":
                        text = ev.get("text", "")
                        partial_md += text
                        await bus.publish(rid, "token", {"text": text, "i": n})
                        n += 1
                        if n % _BUFFER_FLUSH_EVERY == 0:
                            await _flush("generating")
                    elif etype == "section_done":
                        await bus.publish(rid, "section_done", ev)
                        await _flush("generating")
                    elif etype == "report":
                        final_md = ev.get("markdown", "")
                        final_sources = ev.get("sources", [])
                        final_title = ev.get("title", title)
                        await bus.publish(rid, "report", ev)
                    elif etype and etype.startswith("loop_"):
                        # V0.0.5 ② Verifier Loop 全套事件透传给前端
                        # (loop_started / loop_verify_start / loop_verify_done /
                        #  loop_repair_start / loop_repair_done / loop_finished)
                        await bus.publish(rid, etype, ev)
                        await _flush("generating")
                    elif etype == "error":
                        raise RuntimeError(ev.get("message", "研究失败"))

                # 落库最终报告
                if not (final_md or "").strip():
                    raise RuntimeError("研究未产出报告")
                await self._finish(
                    session,
                    report_id,
                    final_title or title or body.topic,
                    final_md,
                    plan_snapshot,
                    final_sources,
                )
            await bus.clear_stream_buffer(rid)
            await bus.publish(rid, "done", {"report_id": rid})
        except Exception as e:
            logger.error("研究后台生成失败: report=%s err=%s", rid, e, exc_info=True)
            await self._fail(report_id, str(e), partial_md, plan_snapshot, sources_brief)
            await bus.clear_stream_buffer(rid)
            await bus.publish(rid, "error", {"message": f"研究失败：{e}"})
        finally:
            await bus.clear_stream_buffer(rid)
            await bus.release_turn_lock(rid, lock_owner)

    # ── 状态/落库辅助 ──

    async def _set_status(
        self, session: AsyncSession, report_id: uuid.UUID, status: str
    ) -> None:
        repo = ResearchReportRepository(session)
        report = await repo.get_by_id(report_id)
        if report:
            report.status = status
            await repo.save(report)

    async def _set_status_safe(self, report_id: uuid.UUID, status: str) -> None:
        """阶段状态回写（独立 session，失败只记 warning，不影响生成）。"""
        valid = {"planning", "searching", "searching_done", "writing", "summarizing"}
        if status not in valid:
            return
        norm = "searching" if status == "searching_done" else status
        try:
            async with SessionLocal() as session:
                await self._set_status(session, report_id, norm)
        except Exception as e:
            logger.warning("研究状态回写失败（忽略）: report=%s err=%s", report_id, e)

    async def _finish(
        self,
        session: AsyncSession,
        report_id: uuid.UUID,
        title: str,
        markdown: str,
        outline: dict | None,
        sources: list,
    ) -> None:
        repo = ResearchReportRepository(session)
        report = await repo.get_by_id(report_id)
        if not report:
            return
        if not (markdown or "").strip():
            raise RuntimeError("research produced no valid report")
        report.title = (title or "")[:255]
        report.report_md = markdown
        report.outline = outline
        report.sources = sources
        report.status = RESEARCH_STATUS_DONE
        report.error_msg = None
        await repo.save(report)
        try:
            if report.status != RESEARCH_STATUS_DONE or not (report.report_md or "").strip():
                logger.info("跳过 GitCode 归档：报告未成功完成 report=%s", report_id)
                return
            archive_url = await GitCodeService().publish_report(report)
            logger.info("研究报告 GitCode 地址: report=%s url=%s", report_id, archive_url)
        except GitCodeNotConfigured:
            logger.warning("研究报告未归档：未配置 GitCode PAT，report=%s", report_id)
        except GitCodePublishError as exc:
            logger.warning("研究报告 GitCode 归档失败，report=%s err=%s", report_id, exc)
        logger.info("研究完成: report=%s title=%s", report_id, report.title)

    async def _fail(
        self,
        report_id: uuid.UUID,
        error_msg: str,
        partial_md: str,
        outline: dict | None,
        sources: list,
    ) -> None:
        """失败落库：保留已产出的部分正文，便于排查/重试。失败只记 warning。"""
        try:
            async with SessionLocal() as session:
                repo = ResearchReportRepository(session)
                report = await repo.get_by_id(report_id)
                if not report:
                    return
                report.status = RESEARCH_STATUS_FAILED
                report.error_msg = error_msg[:2000]
                if partial_md.strip():
                    report.report_md = partial_md
                report.outline = outline
                report.sources = sources
                await repo.save(report)
                await LoopStore(session).fail_running_for_task(report_id, error_msg)
        except Exception as e:
            logger.warning("研究失败落库出错（忽略）: report=%s err=%s", report_id, e)

    # ── 研究指令润色 ──

    async def optimize_topic(self, user_id: uuid.UUID, raw_topic: str) -> str:
        """调用默认对话模型，把口语化/笼统的研究指令润色成清晰可执行的研究主题。

        深度研究主题输入框 + 定时任务「研究指令」共用此接口。失败抛 BizError（中文）。
        """
        from langchain_core.messages import HumanMessage

        from app.core.agent.research.prompt_renderer import render_research_prompt
        from app.core.llm.chat_model import build_default_chat_model

        raw = (raw_topic or "").strip()
        if not raw:
            raise BizError("请先填写要润色的研究指令", code=3060)
        model, _ = await build_default_chat_model(
            self.session, user_id, temperature=0.4, streaming=False
        )
        meta_prompt = render_research_prompt("optimize_topic.jinja2", raw_topic=raw)
        try:
            resp = await model.ainvoke([HumanMessage(content=meta_prompt)])
        except Exception as e:
            logger.warning("研究指令润色失败: user=%s err=%s", user_id, e)
            raise BizError(f"润色失败：{e}", code=3061) from e
        content = resp.content if isinstance(resp.content, str) else str(resp.content)
        optimized = self._strip_code_fence(content.strip())
        if not optimized:
            raise BizError("润色未返回有效内容", code=3062)
        logger.info("研究指令润色成功: user=%s in=%d out=%d", user_id, len(raw), len(optimized))
        return optimized

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """兜底剥离 LLM 可能误加的 ``` 代码块包裹与多余引号。"""
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines).strip()
        # 模型偶尔用引号把整句包起来，去掉首尾成对引号
        if len(t) >= 2 and t[0] in "\"'“”「" and t[-1] in "\"'“”」":
            t = t[1:-1].strip()
        return t

    # ── 配置校验 / 检索范围 ──

    async def _require_websearch(self, user_id: uuid.UUID) -> None:
        from app.core.agent.research.retriever import get_websearch_config

        if not await get_websearch_config(self.session, user_id):
            raise BizError(
                "深度研究依赖联网搜索，请先在「模型配置」添加 websearch 类型模型（百度千帆 / Tavily）",
                code=2010,
            )

    async def _resolve_kb_ids(
        self, user_id: uuid.UUID, kb_ids: list[str] | None
    ) -> list[str] | None:
        """检索知识库范围：显式指定优先，否则用「已启用检索」的库集合。"""
        if kb_ids:
            return kb_ids
        try:
            from app.repositories.knowledge_base_repository import (
                KnowledgeBaseRepository,
            )

            async with SessionLocal() as session:
                return await KnowledgeBaseRepository(session).list_chat_enabled_ids(
                    user_id
                )
        except Exception as e:
            logger.warning("解析研究知识库范围失败（不限库）: %s", e)
            return None

    # ── 管理：列表 / 详情 / 删除 / 存知识库 ──

    async def list_reports(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[dict], int]:
        reports, total = await self.repo.list_paged(user_id, page, page_size)
        return [self.to_brief(r) for r in reports], total

    async def get_detail(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> dict:
        report = await self._get_or_404(user_id, report_id)
        return self.to_detail(report)

    async def notify_report(self, user_id: uuid.UUID, report_id: uuid.UUID) -> dict:
        """手动把已完成的深度研究报告摘要和链接推送到飞书。"""
        report = await self._get_or_404(user_id, report_id)
        if report.status != RESEARCH_STATUS_DONE or not (report.report_md or "").strip():
            raise BizError("报告尚未完成，暂时无法推送", code=3082)

        title = (report.title or report.topic or "深度研究报告").strip()[:120]
        summary = self._extract_report_summary(report.report_md or "")
        try:
            report_url = await GitCodeService().publish_report(report)
        except GitCodeNotConfigured as exc:
            raise BizError("请先配置 GitCode PAT，才能归档并推送完整报告", code=3084) from exc
        except GitCodePublishError as exc:
            raise BizError(f"GitCode 归档失败：{exc}", code=3085) from exc
        content = f"{summary}\n\n查看完整报告：{report_url}"
        if not settings.notify_include_report_link:
            content = summary
        sent = await NotifyService(self.session).push_to_user(
            user_id,
            f"深度研究：{title}",
            content,
            channel_type=CHANNEL_FEISHU,
        )
        if sent == 0:
            raise BizError(
                "没有可用的飞书推送渠道，请先在设置→消息推送中启用飞书机器人",
                code=3083,
            )
        return {
            "sent": sent,
            "channel_type": CHANNEL_FEISHU,
            "repository_url": report_url,
        }

    @staticmethod
    def _extract_report_summary(markdown: str, limit: int = 360) -> str:
        """从 Markdown 正文提取适合消息通知的纯文本摘要。"""
        parts: list[str] = []
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            if line.startswith(">"):
                line = line.lstrip("> ")
            line = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", line)
            line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
            line = re.sub(r"[*_`~]", "", line)
            line = re.sub(r"^[-*+]\s+", "", line)
            if line:
                parts.append(line)
            if len(" ".join(parts)) >= limit:
                break
        text = " ".join(parts).strip()
        return text if len(text) <= limit else f"{text[:limit].rstrip()}…"

    async def get_loop_detail(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> dict | None:
        """V0.0.5 ② Verifier Loop 详情:LoopRun + 各轮 iteration。

        报告生成时未跑 verifier(loop_enabled 关 / engine 异常)→ 返回 None,前端不显示评分卡。
        """
        from app.core.agent.loop.store import LoopStore

        # 先确认报告属于本用户(防越权)
        await self._get_or_404(user_id, report_id)
        store = LoopStore(self.session)
        run = await store.find_latest_by_task(task_type="research", task_id=report_id)
        if run is None:
            return None
        iterations = await store.list_iterations(run.id)
        loop_status = run.status
        loop_note = run.note
        if loop_status == "failed" and is_non_fatal_loop_failure(loop_note):
            loop_status = "passed"
            loop_note = None
        return {
            "run_id": str(run.id),
            "task_type": run.task_type,
            "status": loop_status,
            "iterations": run.iterations,
            "final_score": run.final_score,
            "pass_threshold": run.pass_threshold,
            "max_iterations": run.max_iterations,
            "rubric_name": run.rubric_name,
            "generator_model": run.generator_model,
            "verifier_model": run.verifier_model,
            "verifier_kind": run.verifier_kind,
            "note": loop_note,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "iterations_detail": [
                {
                    "iteration_no": it.iteration_no,
                    "scores": it.scores,           # {raw: {coverage:..., ...}, total: 0.78}
                    "feedback": it.feedback,       # {summary, issues, missing_coverage, ...}
                    "decision": it.decision,
                    "repair_action": it.repair_action,
                    "duration_ms": it.duration_ms,
                    "artifact_snapshot": it.artifact_snapshot,
                }
                for it in iterations
            ],
        }

    async def delete(self, user_id: uuid.UUID, report_id: uuid.UUID) -> None:
        report = await self._get_or_404(user_id, report_id)
        await self.repo.delete(report)
        logger.info("删除研究报告: user=%s id=%s", user_id, report_id)

    async def save_to_kb(
        self, user_id: uuid.UUID, report_id: uuid.UUID, kb_id: uuid.UUID | None
    ) -> dict:
        """把报告 Markdown 作为文档存入知识库（复用文档入库流水线）。"""
        report = await self._get_or_404(user_id, report_id)
        if not report.report_md or report.status != RESEARCH_STATUS_DONE:
            raise BizError("报告尚未完成，无法存入知识库", code=3050)

        from app.core.storage import build_file_key, get_storage
        from app.models.document_model import DOC_STATUS_PENDING, Document
        from app.repositories.document_repository import DocumentRepository
        from app.repositories.knowledge_base_repository import KnowledgeBaseRepository

        kb_repo = KnowledgeBaseRepository(self.session)
        if kb_id:
            kb = await kb_repo.get(user_id, kb_id)
            if not kb:
                raise BizError("知识库不存在", code=3040, status_code=404)
            resolved_kb = kb.id
            kb_name = kb.name
        else:
            # 默认落入专门的「深度研究报告」知识库（不污染其他库）
            kb = await kb_repo.ensure_named(
                user_id,
                "深度研究报告",
                description="深度研究自动生成的报告归档于此",
                icon="🔬",
                color="#7C4DFF",
                chat_enabled=True,
            )
            resolved_kb = kb.id
            kb_name = kb.name

        title = report.title or report.topic[:50] or "研究报告"
        text = report.report_md
        doc_id = uuid.uuid4()
        file_key = build_file_key(str(user_id), "documents", str(doc_id), ".md")
        await get_storage().save(file_key, text.encode("utf-8"))
        doc = Document(
            id=doc_id,
            user_id=user_id,
            kb_id=resolved_kb,
            file_name=f"{title}.md",
            file_ext=".md",
            file_size=len(text.encode("utf-8")),
            file_key=file_key,
            source_type="file",
            status=DOC_STATUS_PENDING,
        )
        await DocumentRepository(self.session).create(doc)
        # 派发解析（延迟导入，避免 worker 未装影响）
        from app.tasks.parse import parse_document_task

        parse_document_task.delay(str(doc_id))
        logger.info("研究报告存入知识库: report=%s doc=%s kb=%s", report_id, doc_id, resolved_kb)
        return {"document_id": str(doc_id), "kb_id": str(resolved_kb), "kb_name": kb_name}

    async def _get_or_404(
        self, user_id: uuid.UUID, report_id: uuid.UUID
    ) -> ResearchReport:
        report = await self.repo.get(user_id, report_id)
        if not report:
            raise BizError("研究报告不存在", code=3051, status_code=404)
        return report

    @staticmethod
    def to_brief(r: ResearchReport) -> dict:
        return {
            "id": str(r.id),
            "topic": r.topic,
            "title": r.title,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    @staticmethod
    def to_detail(r: ResearchReport) -> dict:
        return {
            "id": str(r.id),
            "topic": r.topic,
            "title": r.title,
            "status": r.status,
            "report_md": r.report_md,
            "outline": r.outline,
            "sources": r.sources or [],
            "error_msg": r.error_msg,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
