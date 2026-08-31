"""Memory ORM 模型 —— PostgreSQL memories 表（记忆原文与溯源）。

图谱结构在 Neo4j；本表存每次萃取的来源原文与审计信息，
便于展示「这条记忆从哪段对话/主动记住来」以及关联了哪些图谱实体。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 记忆来源
MEMORY_SOURCE_AUTO = "auto"  # 对话自动萃取
MEMORY_SOURCE_MANUAL = "manual"  # 主动记住

# 萃取状态
MEMORY_STATUS_PENDING = "pending"
MEMORY_STATUS_EXTRACTING = "extracting"
MEMORY_STATUS_DONE = "done"
MEMORY_STATUS_FAILED = "failed"


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)  # 原始陈述/来源文本
    source: Mapped[str] = mapped_column(String(16), default=MEMORY_SOURCE_MANUAL)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # 来源对话消息（对话萃取时填，阶段5 接入）
    status: Mapped[str] = mapped_column(
        String(16), default=MEMORY_STATUS_PENDING, index=True
    )
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 图谱溯源：本次萃取在 Neo4j 写入的 dialogue / 实体 id 等
    graph_dialogue_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    graph_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
