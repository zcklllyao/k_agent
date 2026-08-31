"""情绪记忆路由：当前画像 / 趋势 / 记录 / 分布。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.services.emotion_service import EmotionService

router = APIRouter(prefix="/emotion", tags=["emotion"])


@router.get("/current")
async def get_current_emotion(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = EmotionService(session)
    return success(await service.current(user.id))


@router.get("/trend")
async def get_emotion_trend(
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = EmotionService(session)
    return success(await service.trend(user.id, days))


@router.get("/distribution")
async def get_emotion_distribution(
    days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = EmotionService(session)
    return success(await service.distribution(user.id, days))


@router.get("/records")
async def list_emotion_records(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = EmotionService(session)
    return success(await service.records(user.id, limit, offset))
