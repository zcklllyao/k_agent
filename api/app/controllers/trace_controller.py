"""Agent Trace 控制器 —— /traces 列表 / 详情 / 成本聚合。

权限模型本版默认「只看自己的」,无需 admin 角色;
未来若要做团队/管理员视角再加权限网关。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.trace_schema import CostSummary, TraceDetail, TraceListResponse
from app.services.trace_service import TraceService

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("")
async def list_traces(
    task_type: str | None = Query(None, description="research / chat / agent_task / ..."),
    task_id: uuid.UUID | None = Query(None, description="按业务 task_id 过滤(如某份研究报告/对话)"),
    status: str | None = Query(None, description="running / ok / error"),
    days: int | None = Query(None, ge=1, le=365, description="近 N 天(可选)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Trace 列表(按 started_at 倒序),用于「执行轨迹」入口的列表页。"""
    svc = TraceService(session)
    data: TraceListResponse = await svc.list_traces(
        user.id,
        task_type=task_type,
        task_id=task_id,
        status=status,
        days=days,
        limit=limit,
        offset=offset,
    )
    return success(data)


@router.get("/cost-summary")
async def cost_summary(
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """近 N 天的总 token / 总成本 / 按 task_type 与 model 聚合。"""
    svc = TraceService(session)
    data: CostSummary = await svc.cost_summary(user.id, days=days)
    return success(data)


@router.get("/{trace_id}")
async def get_trace(
    trace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """单条 trace 的详情,含全部 span(供前端时间线 Gantt 视图渲染)。"""
    svc = TraceService(session)
    data: TraceDetail = await svc.get_detail(user.id, trace_id)
    return success(data)
