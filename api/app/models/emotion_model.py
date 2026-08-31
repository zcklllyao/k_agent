"""情绪记忆 ORM 模型 —— PostgreSQL emotion_records / emotion_profiles 表。

每轮对话异步分析用户情绪，结构化存储（离散主情绪 + valence-arousal 维度），
并滚动维护用户「当前情绪画像」，供仪表盘展示和其他情绪分析功能使用。
情绪数据独立于 Neo4j 记忆图谱，仅存 PG。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class EmotionRecord(Base):
    """单轮对话的用户情绪记录。"""

    __tablename__ = "emotion_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    emotion_type: Mapped[str] = mapped_column(String(32), index=True)  # 主情绪（受控词表）
    intensity: Mapped[float] = mapped_column(Float, default=0.0)  # 强度 0~1
    valence: Mapped[float] = mapped_column(Float, default=0.0)  # 效价 -1~1
    arousal: Mapped[float] = mapped_column(Float, default=0.0)  # 唤醒度 0~1
    keywords: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # 情绪关键词
    trigger: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 触发事件
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # 一句话描述
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class EmotionProfile(Base):
    """用户当前情绪画像（每用户一条，滚动更新）。"""

    __tablename__ = "emotion_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    dominant_emotion: Mapped[str] = mapped_column(String(32), default="平静")
    avg_valence: Mapped[float] = mapped_column(Float, default=0.0)
    avg_arousal: Mapped[float] = mapped_column(Float, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)  # 聚合所用样本数
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_emotion_profile_user"),
    )
