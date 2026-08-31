"""PersonaGroup ORM 模型 —— 角色卡组（场景）。

把一组角色卡打包成一个可复用的「场景」。
member_persona_ids 引用 agent_personas.id（JSONB 列表，保序）；删卡组不删成员角色。
内置场景（A股投研天团/周末出游策划团）通过一键添加复制成用户自己的卡组（is_builtin=true，可改可删）。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class PersonaGroup(Base):
    __tablename__ = "persona_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # 组名（如「A股投研天团」）
    name: Mapped[str] = mapped_column(String(64))
    # 组描述（一句话说明这组角色干嘛的）
    description: Mapped[str] = mapped_column(Text, default="")
    # 组图标（emoji 或简单标识）
    icon: Mapped[str] = mapped_column(String(16), default="")
    # 成员角色 id 列表（引用 agent_personas，保序），删卡组不删成员
    member_persona_ids: Mapped[list] = mapped_column(JSONB, default=list)
    # 历史兼容字段：旧版本字段，当前角色卡组不使用
    enable_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否由内置场景模板复制而来（标记用途，用户仍可改删）
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    # 列表排序
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
