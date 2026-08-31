"""DailyReview ORM 模型 —— 每日回顾简报。

每用户每天一条：LLM 汇总当日新对话 / 新记忆 / 新文档生成的小结。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "review_date", name="uq_daily_review"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    review_date: Mapped[date] = mapped_column(Date, index=True)
    content: Mapped[str] = mapped_column(Text)  # 简报正文（Markdown）
    # 前瞻关怀句：基于情绪+记忆+洞察生成的一句主动关心/提醒（⑧），可点击「聊聊」开聊
    care: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 统计快照：当日新增对话/记忆/文档数等
    stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
