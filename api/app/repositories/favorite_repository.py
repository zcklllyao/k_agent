"""收藏夹数据访问层。查询强制带 user_id 隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite_model import Favorite


class FavoriteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(
        self, user_id: uuid.UUID, target_type: str, target_id: str
    ) -> Favorite | None:
        result = await self.session.execute(
            select(Favorite).where(
                Favorite.user_id == user_id,
                Favorite.target_type == target_type,
                Favorite.target_id == target_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(
        self, user_id: uuid.UUID, fav_id: uuid.UUID
    ) -> Favorite | None:
        result = await self.session.execute(
            select(Favorite).where(
                Favorite.id == fav_id, Favorite.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, fav: Favorite) -> Favorite:
        self.session.add(fav)
        await self.session.commit()
        await self.session.refresh(fav)
        return fav

    async def list_by_user(
        self, user_id: uuid.UUID, target_type: str | None = None
    ) -> list[Favorite]:
        stmt = select(Favorite).where(Favorite.user_id == user_id)
        if target_type:
            stmt = stmt.where(Favorite.target_type == target_type)
        stmt = stmt.order_by(Favorite.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, fav: Favorite) -> None:
        await self.session.delete(fav)
        await self.session.commit()
