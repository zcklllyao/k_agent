"""Agent Trace / Span 数据访问层 —— 供仪表盘 / 列表 / 详情接口使用。

读侧职责:
- list_traces: 按 user_id + 筛选条件分页列表(时间倒序)
- get_trace + get_spans: 单条 trace 的详情 + 它的全部 span(supplies 时间线视图)
- cost_summary: 按 task_type / model 聚合成本与 token 用量(供仪表盘)

写侧由 `core/agent/tracing/span_recorder` 异步批量执行,不在本仓库代码路径。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_trace_model import AgentSpan, AgentTrace


class AgentTraceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── 列表 ──

    async def list_traces(
        self,
        user_id: uuid.UUID,
        *,
        task_type: str | None = None,
        task_id: uuid.UUID | None = None,
        status: str | None = None,
        days: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentTrace], int]:
        conditions = [AgentTrace.user_id == user_id]
        if task_type:
            conditions.append(AgentTrace.task_type == task_type)
        if task_id:
            conditions.append(AgentTrace.task_id == task_id)
        if status:
            conditions.append(AgentTrace.status == status)
        if days and days > 0:
            since = datetime.now() - timedelta(days=days)
            conditions.append(AgentTrace.started_at >= since)

        cnt_stmt = select(func.count(AgentTrace.id)).where(and_(*conditions))
        total = (await self.session.execute(cnt_stmt)).scalar_one()

        list_stmt = (
            select(AgentTrace)
            .where(and_(*conditions))
            .order_by(AgentTrace.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(list_stmt)).scalars().all()
        return list(rows), int(total or 0)

    # ── 单条详情 ──

    async def get_trace(
        self, user_id: uuid.UUID, trace_id: uuid.UUID
    ) -> AgentTrace | None:
        stmt = select(AgentTrace).where(
            AgentTrace.user_id == user_id,
            AgentTrace.trace_id == trace_id,
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def get_spans_by_trace(
        self, trace_id: uuid.UUID
    ) -> list[AgentSpan]:
        stmt = (
            select(AgentSpan)
            .where(AgentSpan.trace_id == trace_id)
            .order_by(AgentSpan.started_at.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    # ── 成本聚合(供仪表盘)──

    async def cost_summary(
        self, user_id: uuid.UUID, *, days: int = 30
    ) -> dict[str, Any]:
        """按时间窗口聚合总 token / 总成本 / 按 task_type 与 model 分布。"""
        since = datetime.now() - timedelta(days=days)
        base = select(AgentTrace).where(
            AgentTrace.user_id == user_id, AgentTrace.started_at >= since
        )
        traces = list((await self.session.execute(base)).scalars().all())

        total_input = total_output = total_cached = 0
        total_cost = 0.0
        count_by_type: dict[str, int] = {}
        cost_by_type: dict[str, float] = {}
        duration_by_type: dict[str, list[int]] = {}
        fail_by_type: dict[str, int] = {}

        for t in traces:
            total_input += t.total_input_tokens or 0
            total_output += t.total_output_tokens or 0
            total_cached += t.total_cached_tokens or 0
            total_cost = round(total_cost + (t.total_cost_cny or 0.0), 6)
            tt = t.task_type or "unknown"
            count_by_type[tt] = count_by_type.get(tt, 0) + 1
            cost_by_type[tt] = round(cost_by_type.get(tt, 0.0) + (t.total_cost_cny or 0.0), 6)
            if t.duration_ms:
                duration_by_type.setdefault(tt, []).append(t.duration_ms)
            if t.status == "error":
                fail_by_type[tt] = fail_by_type.get(tt, 0) + 1

        # 按 task_type 平均时长 / 失败率
        type_stats: list[dict[str, Any]] = []
        for tt, cnt in count_by_type.items():
            durs = duration_by_type.get(tt, [])
            avg_dur = int(sum(durs) / len(durs)) if durs else 0
            failed = fail_by_type.get(tt, 0)
            type_stats.append(
                {
                    "task_type": tt,
                    "count": cnt,
                    "total_cost_cny": cost_by_type.get(tt, 0.0),
                    "avg_duration_ms": avg_dur,
                    "fail_rate": round(failed / cnt, 4) if cnt else 0.0,
                }
            )
        type_stats.sort(key=lambda x: x["count"], reverse=True)

        # 按 model 聚合(从 span 表更准,这里走 spans 取真实 LLM 调用)
        model_cost = await self._cost_by_model(user_id, since)

        return {
            "days": days,
            "total_traces": len(traces),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cached_tokens": total_cached,
            "total_cost_cny": total_cost,
            "by_task_type": type_stats,
            "by_model": model_cost,
        }

    async def _cost_by_model(
        self, user_id: uuid.UUID, since: datetime
    ) -> list[dict[str, Any]]:
        """从 spans 聚合 model 用量 —— 仅 llm_call span 且 model_name 非空。"""
        # 通过 AgentTrace 限定用户(trace_id 关联)
        stmt = (
            select(
                AgentSpan.model_name,
                func.count(AgentSpan.id).label("calls"),
                func.coalesce(func.sum(AgentSpan.input_tokens), 0).label("input"),
                func.coalesce(func.sum(AgentSpan.output_tokens), 0).label("output"),
                func.coalesce(func.sum(AgentSpan.cached_tokens), 0).label("cached"),
                func.coalesce(func.sum(AgentSpan.cost_cny), 0.0).label("cost"),
            )
            .join(AgentTrace, AgentTrace.trace_id == AgentSpan.trace_id)
            .where(
                AgentTrace.user_id == user_id,
                AgentSpan.started_at >= since,
                AgentSpan.span_type == "llm_call",
                AgentSpan.model_name.isnot(None),
            )
            .group_by(AgentSpan.model_name)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "model": r.model_name,
                "calls": int(r.calls or 0),
                "input_tokens": int(r.input or 0),
                "output_tokens": int(r.output or 0),
                "cached_tokens": int(r.cached or 0),
                "cost_cny": round(float(r.cost or 0.0), 6),
            }
            for r in sorted(rows, key=lambda r: r.cost or 0.0, reverse=True)
        ]
