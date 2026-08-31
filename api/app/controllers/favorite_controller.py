"""收藏夹路由：添加 / 列表 / 取消。"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.favorite_schema import FavoriteCreateRequest
from app.services.favorite_service import FavoriteService

router = APIRouter(prefix="/favorites", tags=["favorite"])


@router.get("")
async def list_favorites(
    target_type: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = FavoriteService(session)
    items = await service.list_favorites(user.id, target_type)
    return success([service.to_out_dict(f) for f in items])


@router.post("")
async def add_favorite(
    body: FavoriteCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = FavoriteService(session)
    fav = await service.add(user.id, body.target_type, body.target_id, body.snapshot)
    return success(service.to_out_dict(fav), "已收藏")


@router.delete("/{fav_id}")
async def remove_favorite(
    fav_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await FavoriteService(session).remove(user.id, fav_id)
    return success(message="已取消收藏")
