"""角色卡组数据访问层。所有查询带 user_id 做数据隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.persona_group_model import PersonaGroup


class PersonaGroupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[PersonaGroup]:
        result = await self.session.execute(
            select(PersonaGroup)
            .where(PersonaGroup.user_id == user_id)
            .order_by(PersonaGroup.sort, PersonaGroup.created_at)
        )
        return list(result.scalars().all())

    async def get(self, user_id: uuid.UUID, group_id: uuid.UUID) -> PersonaGroup | None:
        result = await self.session.execute(
            select(PersonaGroup).where(
                PersonaGroup.id == group_id, PersonaGroup.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(PersonaGroup.id).where(PersonaGroup.user_id == user_id)
        )
        return len(result.all())

    async def add(self, group: PersonaGroup) -> PersonaGroup:
        self.session.add(group)
        await self.session.commit()
        await self.session.refresh(group)
        return group

    async def save(self, group: PersonaGroup) -> PersonaGroup:
        await self.session.commit()
        await self.session.refresh(group)
        return group

    async def delete(self, group: PersonaGroup) -> None:
        await self.session.delete(group)
        await self.session.commit()
