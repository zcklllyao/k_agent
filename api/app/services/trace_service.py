"""Trace 业务服务 —— 把 repository 数据装成 schema 返回。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.repositories.agent_trace_repository import AgentTraceRepository
from app.schemas.trace_schema import (
    CostSummary,
    SpanItem,
    TraceDetail,
    TraceListItem,
    TraceListResponse,
)


class TraceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = AgentTraceRepository(session)

    async def list_traces(
        self,
        user_id: uuid.UUID,
        *,
        task_type: str | None,
        task_id: uuid.UUID | None,
        status: str | None,
        days: int | None,
        limit: int,
        offset: int,
    ) -> TraceListResponse:
        rows, total = await self.repo.list_traces(
            user_id,
            task_type=task_type,
            task_id=task_id,
            status=status,
            days=days,
            limit=limit,
            offset=offset,
        )
        items = [TraceListItem.model_validate(r) for r in rows]
        return TraceListResponse(total=total, items=items)

    async def get_detail(
        self, user_id: uuid.UUID, trace_id: uuid.UUID
    ) -> TraceDetail:
        trace = await self.repo.get_trace(user_id, trace_id)
        if trace is None:
            raise BizError(
                "未找到该执行轨迹,可能不属于当前用户",
                code=4040,
                status_code=404,
            )
        spans = await self.repo.get_spans_by_trace(trace_id)
        return TraceDetail(
            trace_id=trace.trace_id,
            task_type=trace.task_type,
            task_id=trace.task_id,
            task_name=trace.task_name,
            status=trace.status,
            error_message=trace.error_message,
            started_at=trace.started_at,
            finished_at=trace.finished_at,
            duration_ms=trace.duration_ms,
            total_input_tokens=trace.total_input_tokens,
            total_output_tokens=trace.total_output_tokens,
            total_cached_tokens=trace.total_cached_tokens,
            total_cost_cny=trace.total_cost_cny,
            models_used=list(trace.models_used or []),
            loop_run_id=trace.loop_run_id,
            root_span_id=trace.root_span_id,
            attributes=dict(trace.attributes or {}),
            spans=[SpanItem.model_validate(s) for s in spans],
        )

    async def cost_summary(
        self, user_id: uuid.UUID, *, days: int = 30
    ) -> CostSummary:
        data: dict[str, Any] = await self.repo.cost_summary(user_id, days=days)
        return CostSummary(**data)
