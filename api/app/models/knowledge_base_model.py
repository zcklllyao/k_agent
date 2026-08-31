"""KnowledgeBase ORM 模型 —— PostgreSQL knowledge_bases 表（知识库分类）。

一个知识库 = 一组资料（文档 + 图片）的归属容器 + 检索范围。
documents / images 通过 kb_id 归属到某个库；对话时可限定只检索某个库。
每个用户有一个 is_default=True 的默认库（不可删），存量与未指定归属的资料落入默认库。
文档/图片计数在读取时实时统计，不在本表冗余存储，避免计数漂移。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)  # emoji
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 卡片主题色
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # 是否参与对话检索：对话时检索所有 chat_enabled=True 的库。默认库默认开，其余默认关。
    chat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 自动生成的知识库 Markdown 导航索引（不计入 documents）
    overview_file_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    overview_status: Mapped[str] = mapped_column(
        String(16), default="empty", server_default="empty"
    )
    overview_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    overview_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
