"""MCP 服务配置业务：CRUD、测试连接、同步工具清单。

认证敏感信息（token / api_key）入库前 Fernet 加密，出参掩码。
test/sync 通过官方适配器连真实 server 拉工具清单。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools.mcp.loader import fetch_tools_meta
from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.mcp_server_model import (
    AUTH_API_KEY,
    AUTH_BEARER,
    STATUS_ERROR,
    STATUS_OK,
    MCPServer,
)
from app.repositories.mcp_server_repository import MCPServerRepository
from app.schemas.mcp_schema import MCPServerCreate, MCPServerUpdate

logger = get_logger(__name__)


class MCPService:
    def __init__(self, session: AsyncSession):
        self.repo = MCPServerRepository(session)

    async def list_servers(self, user_id: uuid.UUID) -> list[MCPServer]:
        return await self.repo.list_by_user(user_id)

    async def _get_or_404(
        self, user_id: uuid.UUID, server_id: uuid.UUID
    ) -> MCPServer:
        server = await self.repo.get(user_id, server_id)
        if not server:
            raise BizError("MCP 服务不存在", code=4050, status_code=404)
        return server

    @staticmethod
    def _encrypt_auth(auth_type: str, auth_config: dict | None) -> dict | None:
        """把明文认证信息加密入库。"""
        if auth_type == AUTH_BEARER:
            token = (auth_config or {}).get("token")
            if not token:
                raise BizError("Bearer 认证需提供 token", code=4051)
            return {"token": encrypt_secret(token)}
        if auth_type == AUTH_API_KEY:
            cfg = auth_config or {}
            key = cfg.get("key")
            if not key:
                raise BizError("API Key 认证需提供 key", code=4052)
            return {
                "header": cfg.get("header") or "X-API-Key",
                "key": encrypt_secret(key),
            }
        return None

    async def create(
        self, user_id: uuid.UUID, body: MCPServerCreate
    ) -> MCPServer:
        if await self.repo.get_by_name(user_id, body.name):
            raise BizError("同名 MCP 服务已存在", code=4053)
        server = MCPServer(
            user_id=user_id,
            name=body.name,
            transport=body.transport,
            url=body.url,
            auth_type=body.auth_type,
            auth_config=self._encrypt_auth(body.auth_type, body.auth_config),
            enabled=body.enabled,
        )
        created = await self.repo.create(server)
        logger.info("创建 MCP 服务: user=%s name=%s id=%s", user_id, body.name, created.id)
        self._invalidate_cache(user_id)
        return created

    async def update(
        self, user_id: uuid.UUID, server_id: uuid.UUID, body: MCPServerUpdate
    ) -> MCPServer:
        server = await self._get_or_404(user_id, server_id)
        if body.name is not None and body.name != server.name:
            existing = await self.repo.get_by_name(user_id, body.name)
            if existing and existing.id != server.id:
                raise BizError("同名 MCP 服务已存在", code=4053)
            server.name = body.name
        if body.transport is not None:
            server.transport = body.transport
        if body.url is not None:
            server.url = body.url
        if body.enabled is not None:
            server.enabled = body.enabled
        # 认证：传了 auth_type 才动认证；auth_config 为 None 表示沿用旧值
        if body.auth_type is not None:
            server.auth_type = body.auth_type
            if body.auth_config is not None:
                server.auth_config = self._encrypt_auth(
                    body.auth_type, body.auth_config
                )
            elif body.auth_type == "none":
                server.auth_config = None
        saved = await self.repo.save(server)
        self._invalidate_cache(user_id)
        return saved

    async def delete(self, user_id: uuid.UUID, server_id: uuid.UUID) -> None:
        server = await self._get_or_404(user_id, server_id)
        await self.repo.delete(server)
        logger.info("删除 MCP 服务: user=%s id=%s", user_id, server_id)
        self._invalidate_cache(user_id)

    async def toggle(
        self, user_id: uuid.UUID, server_id: uuid.UUID, enabled: bool
    ) -> MCPServer:
        server = await self._get_or_404(user_id, server_id)
        server.enabled = enabled
        saved = await self.repo.save(server)
        self._invalidate_cache(user_id)
        return saved

    @staticmethod
    def _invalidate_cache(user_id: uuid.UUID) -> None:
        """清该用户 MCP 工具缓存（增删改/开关后调用），下次对话重新拉取最新工具。"""
        try:
            from app.core.agent.tools.mcp.loader import invalidate_mcp_cache

            invalidate_mcp_cache(user_id)
        except Exception:
            pass

    async def test(
        self, user_id: uuid.UUID, server_id: uuid.UUID
    ) -> tuple[bool, str, list[dict]]:
        """测试连接：连 server 拉工具清单，回写状态但不持久化 tools_cache。"""
        server = await self._get_or_404(user_id, server_id)
        try:
            tools = await fetch_tools_meta(server)
            server.status = STATUS_OK
            server.last_error = None
            await self.repo.save(server)
            return True, f"连接成功，发现 {len(tools)} 个工具", tools
        except Exception as e:
            server.status = STATUS_ERROR
            server.last_error = str(e)[:1024]
            await self.repo.save(server)
            logger.warning("MCP 测试连接失败: id=%s err=%s", server_id, e)
            return False, f"连接失败：{e}", []

    async def sync(
        self, user_id: uuid.UUID, server_id: uuid.UUID
    ) -> MCPServer:
        """同步工具清单：连 server 拉工具并写 tools_cache。失败抛 BizError。"""
        server = await self._get_or_404(user_id, server_id)
        try:
            tools = await fetch_tools_meta(server)
        except Exception as e:
            server.status = STATUS_ERROR
            server.last_error = str(e)[:1024]
            await self.repo.save(server)
            raise BizError(f"同步失败：{e}", code=4054) from e
        server.tools_cache = tools
        server.status = STATUS_OK
        server.last_error = None
        server.synced_at = datetime.now(timezone.utc)
        return await self.repo.save(server)

    @staticmethod
    def _auth_masked(server: MCPServer) -> str:
        """认证信息掩码展示。"""
        cfg = server.auth_config or {}
        if server.auth_type == AUTH_BEARER and cfg.get("token"):
            try:
                return mask_secret(decrypt_secret(cfg["token"]))
            except Exception:
                return "****"
        if server.auth_type == AUTH_API_KEY and cfg.get("key"):
            try:
                return mask_secret(decrypt_secret(cfg["key"]))
            except Exception:
                return "****"
        return ""

    @classmethod
    def to_out_dict(cls, server: MCPServer) -> dict:
        return {
            "id": str(server.id),
            "name": server.name,
            "transport": server.transport,
            "url": server.url,
            "auth_type": server.auth_type,
            "auth_masked": cls._auth_masked(server),
            "enabled": server.enabled,
            "status": server.status,
            "last_error": server.last_error,
            "tools_cache": server.tools_cache or [],
            "synced_at": server.synced_at.isoformat() if server.synced_at else None,
            "created_at": server.created_at.isoformat(),
        }


__all__ = ["MCPService"]
