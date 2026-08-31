"""Agent 配置数据访问层。每用户一条，按 user_id 查。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config_model import AgentConfig


class AgentConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user(self, user_id: uuid.UUID) -> AgentConfig | None:
        result = await self.session.execute(
            select(AgentConfig).where(AgentConfig.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, config: AgentConfig) -> AgentConfig:
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def save(self, config: AgentConfig) -> AgentConfig:
        await self.session.commit()
        await self.session.refresh(config)
        return config
