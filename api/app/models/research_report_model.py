"""ResearchReport ORM 模型 —— PostgreSQL research_reports 表（深度研究报告）。

存一次深度研究的主题、提纲、最终报告 Markdown、来源列表与状态。
报告独立存储，可一键存入知识库（不直接污染知识库）。
task_id 预留给定时任务（②）关联，本批次为空。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 研究状态
RESEARCH_STATUS_PENDING = "pending"
RESEARCH_STATUS_PLANNING = "planning"
RESEARCH_STATUS_SEARCHING = "searching"
RESEARCH_STATUS_WRITING = "writing"
RESEARCH_STATUS_SUMMARIZING = "summarizing"
RESEARCH_STATUS_DONE = "done"
RESEARCH_STATUS_FAILED = "failed"


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(Text)  # 用户原始一句话需求
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 生成的标题
    status: Mapped[str] = mapped_column(
        String(16), default=RESEARCH_STATUS_PENDING, index=True
    )
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)  # 最终 Markdown
    outline: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 提纲+查询
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # 来源列表
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 预留：关联定时任务（②）；本批次为空
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
