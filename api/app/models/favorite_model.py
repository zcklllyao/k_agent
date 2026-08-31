"""Favorite ORM 模型 —— 收藏夹。

可收藏对话消息 / 文档 / 记忆实体。snapshot 存收藏时的标题/摘要快照，
便于列表直接展示，不必每次回查源对象（源对象删除后仍可见收藏记录）。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 收藏目标类型
FAV_MESSAGE = "message"
FAV_DOCUMENT = "document"
FAV_IMAGE = "image"
FAV_MEMORY = "memory"  # 记忆实体（Neo4j entity id，字符串）


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_favorite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(16))  # message | document | memory
    target_id: Mapped[str] = mapped_column(String(64))  # 源对象 id（UUID 或图谱实体 id）
    # 收藏时的标题/摘要快照，便于列表展示
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
