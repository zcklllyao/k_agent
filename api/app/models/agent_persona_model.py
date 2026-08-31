"""AgentPersona ORM 模型 —— 对话人格（角色卡）。

每用户可建多组人格，每组含组名/头像/人格提示词/温度；
同一时刻仅一组 is_active=true（由 service 层事务保证互斥），
对话时注入该组 system_prompt 与 temperature。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class AgentPersona(Base):
    __tablename__ = "agent_personas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # 组名（如「周杰伦」「严谨助理」）
    name: Mapped[str] = mapped_column(String(64))
    # 头像文件 key（存储 key，非 URL）；为空则该人格不显示 AI 头像
    avatar_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 人格提示词（人设/语气/口头禅），对话时作为 system message 注入
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    # 是否当前生效（每用户最多一条 true，service 层保证互斥）
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 仅作为角色卡组成员存在（如内置场景拉入的角色），不在「单个角色」列表单独展示
    in_group_only: Mapped[bool] = mapped_column(Boolean, default=False)
    # 列表排序（预留）
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
