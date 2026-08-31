"""仪表盘路由：每日回顾（概览统计等阶段8 补充）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.services.daily_review_service import DailyReviewService
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """概览统计：各类计数 + 标签分布 + 最近活动。"""
    return success(await DashboardService(session).overview(user.id))


@router.get("/memory-stats")
async def memory_stats(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """记忆统计：新增趋势 + 社区分布。"""
    return success(await DashboardService(session).memory_stats(user.id))


@router.get("/daily-review")
async def daily_review(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """当日回顾（没有则现场生成）。"""
    data = await DailyReviewService(session).get_or_generate(user.id)
    return success(data)


@router.get("/agent-briefing")
async def agent_briefing(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Agent 简报：最近完成的深度研究报告（含定时任务产出）。"""
    return success(await DashboardService(session).agent_briefing(user.id))


@router.get("/loop-health")
async def loop_health(
    days: int = 30,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """V0.0.5 ② Loop 健康度:近 N 天 Verifier Loop 状态分布 + 一次通过率 + 失败维度归因。"""
    return success(await DashboardService(session).loop_health(user.id, days=days))
