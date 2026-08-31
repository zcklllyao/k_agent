"""ToolConfig ORM 模型 —— 用户对工具的启停配置。

内置工具的「定义」在代码注册表（BUILTIN_REGISTRY），本表只存用户对每个工具的
启停状态与额外配置；无记录时按工具定义的 default_enabled 兜底。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

TOOL_TYPE_BUILTIN = "builtin"
TOOL_TYPE_MCP = "mcp"


class ToolConfig(Base):
    __tablename__ = "tool_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tool_key: Mapped[str] = mapped_column(String(128), index=True)  # 内置工具 key
    tool_type: Mapped[str] = mapped_column(String(16), default=TOOL_TYPE_BUILTIN)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 工具特定配置（预留）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "tool_key", name="uq_tool_user_key"),
    )
