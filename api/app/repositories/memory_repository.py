"""Memory 数据访问层 —— PostgreSQL memories 表（记忆原文与溯源）。"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_model import Memory


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, memory: Memory) -> Memory:
        self.session.add(memory)
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def save(self, memory: Memory) -> Memory:
        await self.session.commit()
        await self.session.refresh(memory)
        return memory

    async def get_by_id(self, memory_id: uuid.UUID) -> Memory | None:
        result = await self.session.execute(
            select(Memory).where(Memory.id == memory_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: uuid.UUID, page: int, page_size: int
    ) -> tuple[list[Memory], int]:
        base = select(Memory).where(Memory.user_id == user_id)
        total = await self.session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        result = await self.session.execute(
            base.order_by(Memory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), int(total or 0)

    async def delete(self, memory: Memory) -> None:
        await self.session.delete(memory)
        await self.session.commit()
