"""对话人格数据访问层。所有查询带 user_id 做数据隔离。"""
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_persona_model import AgentPersona


class AgentPersonaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[AgentPersona]:
        result = await self.session.execute(
            select(AgentPersona)
            .where(AgentPersona.user_id == user_id)
            .order_by(AgentPersona.sort, AgentPersona.created_at)
        )
        return list(result.scalars().all())

    async def get(self, user_id: uuid.UUID, persona_id: uuid.UUID) -> AgentPersona | None:
        result = await self.session.execute(
            select(AgentPersona).where(
                AgentPersona.id == persona_id, AgentPersona.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def get_active(self, user_id: uuid.UUID) -> AgentPersona | None:
        result = await self.session.execute(
            select(AgentPersona).where(
                AgentPersona.user_id == user_id, AgentPersona.is_active.is_(True)
            )
        )
        return result.scalars().first()

    async def count(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(AgentPersona.id).where(AgentPersona.user_id == user_id)
        )
        return len(result.all())

    async def add(self, persona: AgentPersona) -> AgentPersona:
        self.session.add(persona)
        await self.session.commit()
        await self.session.refresh(persona)
        return persona

    async def save(self, persona: AgentPersona) -> AgentPersona:
        await self.session.commit()
        await self.session.refresh(persona)
        return persona

    async def delete(self, persona: AgentPersona) -> None:
        await self.session.delete(persona)
        await self.session.commit()

    async def deactivate_all(self, user_id: uuid.UUID) -> None:
        """把该用户所有人格的 is_active 置 false（不提交，由调用方统一提交）。"""
        await self.session.execute(
            update(AgentPersona)
            .where(AgentPersona.user_id == user_id, AgentPersona.is_active.is_(True))
            .values(is_active=False)
        )
