"""工具配置业务服务：列出工具 + 启停。

工具「定义」来自代码注册表（内置）与 MCP（后续接入）；本服务负责把定义与
用户的持久启停状态（tool_configs 表）组合返回，并处理启停写入。
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools import list_tools_for_user
from app.core.agent.tools.base import BUILTIN_REGISTRY
from app.core.exceptions import BizError
from app.models.tool_config_model import TOOL_TYPE_BUILTIN
from app.repositories.tool_config_repository import ToolConfigRepository


class ToolService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ToolConfigRepository(session)

    async def list_tools(self, user_id: uuid.UUID) -> list[dict]:
        """列出全部工具（内置 + 用户启停状态）。"""
        return await list_tools_for_user(self.session, user_id)

    async def set_enabled(
        self, user_id: uuid.UUID, tool_key: str, enabled: bool
    ) -> dict:
        """启停某个工具。校验工具存在。"""
        if tool_key not in BUILTIN_REGISTRY:
            raise BizError("工具不存在", code=4040, status_code=404)
        await self.repo.upsert(
            user_id, tool_key, enabled, tool_type=TOOL_TYPE_BUILTIN
        )
        return {"tool_key": tool_key, "enabled": enabled}


__all__ = ["ToolService"]
