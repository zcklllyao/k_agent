"""MessageFeedback ORM 模型 —— AI 回复的赞/踩反馈。

每个用户对每条消息最多一条反馈（user_id + message_id 唯一），可切换赞/踩或取消。
用于「回答质量评估」：沉淀用户对回答的正负反馈，供后续分析与优化。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 反馈类型
FEEDBACK_UP = "up"  # 赞
FEEDBACK_DOWN = "down"  # 踩


class MessageFeedback(Base):
    __tablename__ = "message_feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    rating: Mapped[str] = mapped_column(String(8))  # up | down
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)  # 可选文字反馈
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),
    )
