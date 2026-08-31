"""MCPServer ORM 模型 —— 用户配置的外部 MCP 服务。

每个 server 是一组远程工具的来源（远程 SSE / Streamable HTTP 传输）。
认证信息（token / api_key）用 Fernet 加密存 auth_config；接口返回掩码。
工具清单同步后缓存在 tools_cache，启停粒度为 server 级。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 传输类型
TRANSPORT_SSE = "sse"
TRANSPORT_STREAMABLE_HTTP = "streamable_http"

# 认证类型
AUTH_NONE = "none"
AUTH_BEARER = "bearer"
AUTH_API_KEY = "api_key"

# 连接状态
STATUS_UNKNOWN = "unknown"
STATUS_OK = "ok"
STATUS_ERROR = "error"


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))  # 服务显示名（拼工具名前缀用）
    transport: Mapped[str] = mapped_column(String(32), default=TRANSPORT_STREAMABLE_HTTP)
    url: Mapped[str] = mapped_column(String(512))
    auth_type: Mapped[str] = mapped_column(String(16), default=AUTH_NONE)
    # 认证敏感信息：{"token": "<Fernet密文>"} 或 {"header": "X-Api-Key", "key": "<密文>"}
    auth_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_UNKNOWN)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # 同步下来的工具清单：[{"name","description"}]
    tools_cache: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_mcp_user_name"),
    )
