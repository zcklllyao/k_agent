"""技能数据访问层。所有查询带 user_id 做数据隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_model import Skill


class SkillRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[Skill]:
        result = await self.session.execute(
            select(Skill)
            .where(Skill.user_id == user_id)
            .order_by(Skill.sort, Skill.created_at)
        )
        return list(result.scalars().all())

    async def get(self, user_id: uuid.UUID, skill_id: uuid.UUID) -> Skill | None:
        result = await self.session.execute(
            select(Skill).where(Skill.id == skill_id, Skill.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(Skill.id).where(Skill.user_id == user_id)
        )
        return len(result.all())

    async def add(self, skill: Skill) -> Skill:
        self.session.add(skill)
        await self.session.commit()
        await self.session.refresh(skill)
        return skill

    async def save(self, skill: Skill) -> Skill:
        await self.session.commit()
        await self.session.refresh(skill)
        return skill

    async def delete(self, skill: Skill) -> None:
        await self.session.delete(skill)
        await self.session.commit()
