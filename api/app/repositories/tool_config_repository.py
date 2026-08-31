"""工具配置数据访问层。查询强制带 user_id 隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tool_config_model import ToolConfig


class ToolConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(self, user_id: uuid.UUID) -> list[ToolConfig]:
        result = await self.session.execute(
            select(ToolConfig).where(ToolConfig.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get(self, user_id: uuid.UUID, tool_key: str) -> ToolConfig | None:
        result = await self.session.execute(
            select(ToolConfig).where(
                ToolConfig.user_id == user_id, ToolConfig.tool_key == tool_key
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: uuid.UUID,
        tool_key: str,
        enabled: bool,
        tool_type: str = "builtin",
        config: dict | None = None,
    ) -> ToolConfig:
        existing = await self.get(user_id, tool_key)
        if existing:
            existing.enabled = enabled
            if config is not None:
                existing.config = config
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        row = ToolConfig(
            user_id=user_id,
            tool_key=tool_key,
            tool_type=tool_type,
            enabled=enabled,
            config=config,
        )
        self.session.add(row)
        await self.session.commit()
        await self.session.refresh(row)
        return row
