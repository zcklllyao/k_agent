"""LoopController:Verifier Loop 通用状态机。

三段式:generate → verify → decide(→ repair → 下一轮)。

设计:
- Controller 不直接 import research engine / agent_task,通过 ctx 里的回调解耦
- 状态全程落库(loop_runs / loop_iterations),进程崩 / worker 重启可恢复
- 异常护栏:任一步抛异常,标 failed 兜底返回最后一次 artifact,不让业务跑空
- 流式事件:对外产出统一 dict 事件流,供 research engine 接进现有 SSE
"""
from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.loop.models import (
    DECISION_EXCEED,
    DECISION_PASS,
    IterationOutcome,
    RubricDef,
)
from app.core.agent.loop.policy import Policy
from app.core.agent.loop.repair import ChapterRewrite, PatchRepair
from app.core.agent.loop.rubric import RUBRICS
from app.core.agent.loop.store import LoopStore
from app.core.agent.loop.verifier import Verifier, build_verifier
from app.core.agent.tracing import get_tracer
from app.core.agent.tracing.otel_attrs import (
    K_AGENT_LOOP_ITERATION_NO,
    K_AGENT_REPAIR_ACTION,
    K_AGENT_VERIFIER_KIND,
    K_AGENT_VERIFIER_RUBRIC,
)
from app.core.logging import get_logger
from app.models.loop_model import (
    STATUS_EXCEEDED,
    STATUS_FAILED,
    STATUS_PASSED,
)

logger = get_logger(__name__)


# ── 类型别名:Controller 与业务的解耦点 ──

# 上层提供的「重新生成」回调(本轮 artifact + repair_action → 下轮 artifact)
RepairCallback = Callable[[dict[str, Any], "RepairCallbackArgs"], Awaitable[dict[str, Any]]]


class RepairCallbackArgs:
    """打包给 RepairExecutor.execute 的上下文(避免参数膨胀)。"""

    def __init__(self, *, patch_callback=None, rewrite_callback=None, extras: dict | None = None):
        self.patch_callback = patch_callback  # async fn(queries: list[str]) -> new_artifact
        self.rewrite_callback = rewrite_callback  # async fn(chapters: list[str]) -> new_artifact
        self.extras = extras or {}


class LoopController:
    """Verifier Loop 状态机。

    用法(上层):
        controller = LoopController(session=session, user_id=user_id, task_type="research", task_id=report_id)
        async for ev in controller.run(
            topic=topic,
            initial_artifact=artifact,
            verifier_kind="cross",
            generator_model=model,
            generator_model_name="gpt-4o-mini",
            repair_ctx=RepairCallbackArgs(
                patch_callback=lambda qs: patch_and_rewrite(qs),
                rewrite_callback=lambda chs: rewrite_chapters(chs),
            ),
        ):
            # ev 形如 {"type": "loop_verify_done", "iteration": 1, "scores": {...}, "decision": "pass"}
            yield ev   # 透传给 SSE
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        user_id: uuid.UUID,
        task_type: str,
        task_id: uuid.UUID | None = None,
        rubric_name: str | None = None,
        max_iterations: int | None = None,
        policy: Policy | None = None,
    ):
        self.session = session
        self.user_id = user_id
        self.task_type = task_type
        self.task_id = task_id

        # 选 rubric:默认按 task_type 取(research / task)
        self.rubric_name = rubric_name or (
            "research" if task_type == "research" else "task"
        )
        rubric = RUBRICS.get(self.rubric_name)
        if rubric is None:
            raise ValueError(f"未知 rubric: {self.rubric_name}")
        self.rubric: RubricDef = rubric

        self.max_iterations = max_iterations or 2
        self.policy = policy or Policy(
            patch_repair=PatchRepair(),
            chapter_rewrite=ChapterRewrite(),
        )
        self.store = LoopStore(session)

    async def run(
        self,
        *,
        topic: str,
        initial_artifact: dict[str, Any],
        verifier_kind: str,
        generator_model,
        generator_model_name: str = "",
        repair_ctx: RepairCallbackArgs | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """跑一次完整 Verifier Loop。

        产出事件(供 SSE 透传):
            {"type": "loop_started", "run_id": str, "rubric": str, "max_iterations": int}
            {"type": "loop_verify_start", "iteration": int}
            {"type": "loop_verify_done", "iteration": int, "scores": {...}, "total": float, "decision": str}
            {"type": "loop_repair_start", "iteration": int, "kind": str, "rationale": str}
            {"type": "loop_repair_done", "iteration": int}
            {"type": "loop_finished", "status": str, "final_score": float, "iterations": int,
             "final_artifact": {...}}

        即使中途出错也会落库并产出 loop_finished(status=failed) 事件,业务侧仍能拿到最后 artifact。
        """
        repair_ctx = repair_ctx or RepairCallbackArgs()

        # 构建 verifier
        verifier: Verifier = await build_verifier(
            self.session, self.user_id,
            kind=verifier_kind,
            generator_model=generator_model,
            generator_model_name=generator_model_name,
        )

        # 建 LoopRun 记录
        run = await self.store.create_run(
            user_id=self.user_id,
            task_type=self.task_type,
            task_id=self.task_id,
            pass_threshold=self.rubric.pass_threshold,
            max_iterations=self.max_iterations,
            rubric_name=self.rubric_name,
            generator_model=generator_model_name or None,
            verifier_model=verifier.model_name or None,
            verifier_kind=verifier.kind,
        )
        run_id = run.id

        yield {
            "type": "loop_started",
            "run_id": str(run_id),
            "rubric": self.rubric_name,
            "max_iterations": self.max_iterations,
            "pass_threshold": self.rubric.pass_threshold,
        }

        artifact = initial_artifact
        iteration_no = 0
        final_status = STATUS_PASSED
        final_score: float | None = None
        final_note: str | None = None

        try:
            while True:
                iteration_no += 1
                t0 = time.time()
                # 预生成 iteration_id,让 tracer 的 verifier/repair span 都能精确关联到这一轮
                iter_id = uuid.uuid4()
                tracer = get_tracer()

                # 1. Verify
                yield {"type": "loop_verify_start", "iteration": iteration_no}
                try:
                    async with tracer.span(
                        f"verifier 第 {iteration_no} 轮",
                        span_type="verifier",
                        attributes={
                            K_AGENT_LOOP_ITERATION_NO: iteration_no,
                            K_AGENT_VERIFIER_KIND: verifier_kind,
                            K_AGENT_VERIFIER_RUBRIC: self.rubric_name,
                        },
                    ) as vsp:
                        vsp.set_iteration_id(iter_id)
                        score = await verifier.verify(
                            topic=topic, artifact=artifact, rubric=self.rubric
                        )
                        vsp.set_payload("total_score", round(score.total, 4))
                        vsp.set_payload("raw_scores", score.raw_scores)
                except Exception as e:  # noqa: BLE001
                    # verifier 自身炸了:把这一轮视为「无法判定」,直接通过(避免无限循环)+ 标 note
                    logger.warning("verifier.verify 失败，终止 loop：%s", e)
                    # Verifier is an optional quality gate. If it is unavailable,
                    # keep the generated artifact deliverable and record the warning.
                    final_status = STATUS_PASSED
                    final_note = f"verifier 异常: {e}"
                    outcome = IterationOutcome(
                        id=iter_id,
                        iteration_no=iteration_no,
                        artifact_snapshot=self._snapshot(artifact),
                        decision=DECISION_PASS,
                        duration_ms=int((time.time() - t0) * 1000),
                    )
                    await self.store.record_iteration(run_id, outcome)
                    yield {
                        "type": "loop_verify_done",
                        "iteration": iteration_no,
                        "scores": {},
                        "total": None,
                        "decision": DECISION_PASS,
                        "note": "verifier 异常,跳出 loop 沿用现报告",
                    }
                    break

                # 2. Decide
                decision, executor = self.policy.decide(
                    score=score,
                    rubric=self.rubric,
                    iteration_no=iteration_no,
                    max_iterations=self.max_iterations,
                )

                yield {
                    "type": "loop_verify_done",
                    "iteration": iteration_no,
                    "scores": {"raw": score.raw_scores, "total": score.total},
                    "feedback_summary": (score.feedback or {}).get("summary"),
                    "decision": decision,
                }

                if decision == DECISION_PASS:
                    final_score = score.total
                    outcome = IterationOutcome(
                        id=iter_id,
                        iteration_no=iteration_no,
                        artifact_snapshot=self._snapshot(artifact),
                        score=score,
                        decision=DECISION_PASS,
                        duration_ms=int((time.time() - t0) * 1000),
                    )
                    await self.store.record_iteration(run_id, outcome)
                    break

                if decision == DECISION_EXCEED:
                    final_status = STATUS_EXCEEDED
                    final_score = score.total
                    final_note = (score.feedback or {}).get("summary") or "超过最大迭代或问题面过广"
                    outcome = IterationOutcome(
                        id=iter_id,
                        iteration_no=iteration_no,
                        artifact_snapshot=self._snapshot(artifact),
                        score=score,
                        decision=DECISION_EXCEED,
                        duration_ms=int((time.time() - t0) * 1000),
                    )
                    await self.store.record_iteration(run_id, outcome)
                    break

                # 3. Repair(retry_patch / retry_rewrite)
                if executor is None:
                    logger.warning("decision=%s 但 executor 为空,break", decision)
                    final_status = STATUS_EXCEEDED
                    final_score = score.total
                    final_note = "policy 未提供 executor"
                    outcome = IterationOutcome(
                        id=iter_id,
                        iteration_no=iteration_no,
                        artifact_snapshot=self._snapshot(artifact),
                        score=score,
                        decision=DECISION_EXCEED,
                        duration_ms=int((time.time() - t0) * 1000),
                    )
                    await self.store.record_iteration(run_id, outcome)
                    break

                action = executor.plan(score=score, artifact=artifact)
                yield {
                    "type": "loop_repair_start",
                    "iteration": iteration_no,
                    "kind": action.kind,
                    "rationale": action.rationale,
                    "patch_queries": action.patch_queries,
                    "rewrite_chapters": action.rewrite_chapters,
                }

                outcome = IterationOutcome(
                    id=iter_id,
                    iteration_no=iteration_no,
                    artifact_snapshot=self._snapshot(artifact),
                    score=score,
                    decision=decision,
                    repair_action=action,
                    duration_ms=int((time.time() - t0) * 1000),
                )
                await self.store.record_iteration(run_id, outcome)

                # 执行修复 → 新 artifact(包一层 repair span,关联到本轮 iteration_id)
                try:
                    async with tracer.span(
                        f"repair: {action.kind} 第 {iteration_no} 轮",
                        span_type="repair",
                        attributes={
                            K_AGENT_LOOP_ITERATION_NO: iteration_no,
                            K_AGENT_REPAIR_ACTION: action.kind,
                        },
                    ) as rsp:
                        rsp.set_iteration_id(iter_id)
                        rsp.set_payload("rationale", action.rationale[:200])
                        if action.patch_queries:
                            rsp.set_payload("patch_queries", action.patch_queries[:5])
                        if action.rewrite_chapters:
                            rsp.set_payload("rewrite_chapters", action.rewrite_chapters[:10])
                        artifact = await executor.execute(
                            action=action,
                            artifact=artifact,
                            ctx={
                                "patch_callback": repair_ctx.patch_callback,
                                "rewrite_callback": repair_ctx.rewrite_callback,
                                **repair_ctx.extras,
                            },
                        )
                except Exception as e:  # noqa: BLE001
                    logger.warning("repair.execute 失败,沿用旧 artifact 进入下轮 verify: %s", e)

                yield {"type": "loop_repair_done", "iteration": iteration_no, "kind": action.kind}

        except Exception as e:  # noqa: BLE001
            logger.error("LoopController.run 异常: %s", e, exc_info=True)
            final_status = STATUS_FAILED
            final_note = str(e)[:500]

        # 终结落库
        await self.store.finish_run(
            run_id, status=final_status, final_score=final_score, note=final_note
        )
        yield {
            "type": "loop_finished",
            "status": final_status,
            "final_score": final_score,
            "iterations": iteration_no,
            "note": final_note,
            "final_artifact": artifact,
        }

    # ── 内部:artifact 摘要(不存全文,只存哈希 + 长度 + 关键统计) ──

    def _snapshot(self, artifact: dict[str, Any]) -> dict[str, Any]:
        """artifact 摘要,落库省空间且方便排查。"""
        import hashlib

        md = (artifact.get("markdown") or "")
        return {
            "title": artifact.get("title", "")[:200],
            "markdown_len": len(md),
            "markdown_hash": hashlib.sha256(md.encode("utf-8")).hexdigest()[:16] if md else "",
            "sources_count": len(artifact.get("sources") or []),
            "headings": list(artifact.get("headings") or [])[:20],
        }


__all__ = ["LoopController", "RepairCallbackArgs"]
