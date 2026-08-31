"""MCP 服务配置数据访问层。查询强制带 user_id 隔离。"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_server_model import MCPServer


class MCPServerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_user(
        self, user_id: uuid.UUID, enabled_only: bool = False
    ) -> list[MCPServer]:
        stmt = select(MCPServer).where(MCPServer.user_id == user_id)
        if enabled_only:
            stmt = stmt.where(MCPServer.enabled.is_(True))
        stmt = stmt.order_by(MCPServer.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(
        self, user_id: uuid.UUID, server_id: uuid.UUID
    ) -> MCPServer | None:
        stmt = select(MCPServer).where(
            MCPServer.id == server_id, MCPServer.user_id == user_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> MCPServer | None:
        stmt = select(MCPServer).where(
            MCPServer.user_id == user_id, MCPServer.name == name
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, server: MCPServer) -> MCPServer:
        self.session.add(server)
        await self.session.commit()
        await self.session.refresh(server)
        return server

    async def save(self, server: MCPServer) -> MCPServer:
        await self.session.commit()
        await self.session.refresh(server)
        return server

    async def delete(self, server: MCPServer) -> None:
        await self.session.delete(server)
        await self.session.commit()
