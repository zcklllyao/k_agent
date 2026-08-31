"""收藏夹业务服务：添加/取消/列表。

target_type 限定 message / document / memory；同一目标重复收藏直接返回已有记录（幂等）。
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.models.favorite_model import (
    FAV_DOCUMENT,
    FAV_IMAGE,
    FAV_MEMORY,
    FAV_MESSAGE,
    Favorite,
)
from app.repositories.favorite_repository import FavoriteRepository

_VALID_TYPES = {FAV_MESSAGE, FAV_DOCUMENT, FAV_IMAGE, FAV_MEMORY}


class FavoriteService:
    def __init__(self, session: AsyncSession):
        self.repo = FavoriteRepository(session)

    async def add(
        self,
        user_id: uuid.UUID,
        target_type: str,
        target_id: str,
        snapshot: dict | None = None,
    ) -> Favorite:
        if target_type not in _VALID_TYPES:
            raise BizError("不支持的收藏类型", code=6001)
        existing = await self.repo.get(user_id, target_type, target_id)
        if existing:
            return existing
        return await self.repo.create(
            Favorite(
                user_id=user_id,
                target_type=target_type,
                target_id=target_id,
                snapshot=snapshot,
            )
        )

    async def list_favorites(
        self, user_id: uuid.UUID, target_type: str | None = None
    ) -> list[Favorite]:
        return await self.repo.list_by_user(user_id, target_type)

    async def remove(self, user_id: uuid.UUID, fav_id: uuid.UUID) -> None:
        fav = await self.repo.get_by_id(user_id, fav_id)
        if not fav:
            raise BizError("收藏不存在", code=6002, status_code=404)
        await self.repo.delete(fav)

    @staticmethod
    def to_out_dict(fav: Favorite) -> dict:
        return {
            "id": str(fav.id),
            "target_type": fav.target_type,
            "target_id": fav.target_id,
            "snapshot": fav.snapshot,
            "created_at": fav.created_at.isoformat() if fav.created_at else None,
        }
