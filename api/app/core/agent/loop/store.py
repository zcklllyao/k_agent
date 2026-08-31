"""Verifier Loop 状态外置层 —— 落库 / 恢复 / 查询。

Controller 不直接操作 ORM,所有 DB 访问走这里。这样:
- Controller 保持纯,便于单元测试(可 mock store)
- 落库逻辑集中,异常处理统一
- 未来切换存储(如 Redis 缓存 + PG 持久化)只改这一处
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.loop.models import IterationOutcome
from app.core.logging import get_logger
from app.models.loop_model import (
    STATUS_EXCEEDED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_RUNNING,
    LoopIteration,
    LoopRun,
)

logger = get_logger(__name__)


class LoopStore:
    """Loop 状态持久化封装。所有方法都吞 DB 异常不阻断主流程(只记 warning),
    因为「状态记不上」比「业务停摆」代价小。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── 创建 / 状态流转 ──

    async def create_run(
        self,
        *,
        user_id: uuid.UUID,
        task_type: str,
        task_id: uuid.UUID | None,
        pass_threshold: float,
        max_iterations: int,
        rubric_name: str | None = None,
        generator_model: str | None = None,
        verifier_model: str | None = None,
        verifier_kind: str | None = None,
    ) -> LoopRun:
        run = LoopRun(
            user_id=user_id,
            task_type=task_type,
            task_id=task_id,
            status=STATUS_RUNNING,
            iterations=0,
            pass_threshold=pass_threshold,
            max_iterations=max_iterations,
            rubric_name=rubric_name,
            generator_model=generator_model,
            verifier_model=verifier_model,
            verifier_kind=verifier_kind,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def record_iteration(
        self, run_id: uuid.UUID, outcome: IterationOutcome
    ) -> None:
        """落库一轮迭代记录,同时更新 LoopRun 的 iterations 计数。"""
        try:
            it = LoopIteration(
                id=outcome.id,  # 用 outcome 预生成的 id,便于 tracer span 关联
                run_id=run_id,
                iteration_no=outcome.iteration_no,
                artifact_snapshot=outcome.artifact_snapshot,
                scores={
                    "raw": outcome.score.raw_scores,
                    "total": outcome.score.total,
                },
                feedback=outcome.score.feedback,
                decision=outcome.decision,
                repair_action=(
                    outcome.repair_action.model_dump() if outcome.repair_action else None
                ),
                duration_ms=outcome.duration_ms,
            )
            self.session.add(it)
            # 顺手把 run 的 iterations 计数推进
            run = await self.session.get(LoopRun, run_id)
            if run is not None:
                run.iterations = outcome.iteration_no
            await self.session.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("LoopStore.record_iteration 失败: %s", e)
            await self.session.rollback()

    async def finish_run(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        final_score: float | None,
        note: str | None = None,
    ) -> None:
        """终结一次 Loop:passed / exceeded / failed。"""
        try:
            run = await self.session.get(LoopRun, run_id)
            if run is None:
                return
            run.status = status
            run.final_score = final_score
            run.finished_at = datetime.now(UTC)
            if note:
                run.note = note[:2000]  # 防御性截断
            await self.session.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("LoopStore.finish_run 失败: %s", e)
            await self.session.rollback()

    # ── 查询(给前端 audit / 仪表盘) ──

    async def fail_running_for_task(self, task_id: uuid.UUID, note: str) -> int:
        """Close loop runs left in ``running`` after a research timeout/crash."""
        try:
            stmt = select(LoopRun).where(
                LoopRun.task_id == task_id,
                LoopRun.status == STATUS_RUNNING,
            )
            result = await self.session.execute(stmt)
            runs = list(result.scalars().all())
            now = datetime.now(UTC)
            for run in runs:
                run.status = STATUS_FAILED
                run.finished_at = now
                run.note = (note or "research task failed")[:2000]
            if runs:
                await self.session.commit()
            return len(runs)
        except Exception as e:  # noqa: BLE001
            logger.warning("LoopStore.fail_running_for_task failed: %s", e)
            await self.session.rollback()
            return 0

    async def get_run(self, run_id: uuid.UUID) -> LoopRun | None:
        return await self.session.get(LoopRun, run_id)

    async def list_iterations(self, run_id: uuid.UUID) -> list[LoopIteration]:
        stmt = (
            select(LoopIteration)
            .where(LoopIteration.run_id == run_id)
            .order_by(LoopIteration.iteration_no.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_latest_by_task(
        self, *, task_type: str, task_id: uuid.UUID
    ) -> LoopRun | None:
        """按业务 task_id 找最近一次 Loop(供前端展示「质量评分卡」用)。"""
        stmt = (
            select(LoopRun)
            .where(LoopRun.task_type == task_type)
            .where(LoopRun.task_id == task_id)
            .order_by(LoopRun.started_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


# 便利常量重导出
__all__ = [
    "LoopStore",
    "STATUS_RUNNING",
    "STATUS_PASSED",
    "STATUS_FAILED",
    "STATUS_EXCEEDED",
]
