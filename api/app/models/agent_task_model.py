"""AgentTask ORM 模型 —— PostgreSQL agent_tasks 表（定时/主动研究任务）。

用户建一个任务：自然语言指令 + 触发规则；到点由 Celery beat 心跳扫表派发，
自动跑深度研究引擎产出报告（报告存 research_reports，task_id 关联本任务）。
运行历史 = research_reports 中 task_id == 本任务的记录，不另建表。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 触发类型
TRIGGER_DAILY = "daily"  # 每天 HH:MM
TRIGGER_WEEKLY = "weekly"  # 每周某天 HH:MM
TRIGGER_INTERVAL = "interval"  # 每隔 N 小时

# 最近一次运行状态
TASK_RUN_NONE = ""
TASK_RUN_RUNNING = "running"
TASK_RUN_DONE = "done"
TASK_RUN_FAILED = "failed"


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))  # 任务名
    instruction: Mapped[str] = mapped_column(Text)  # 自然语言研究指令/主题
    kb_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # 检索范围，空=默认

    trigger_type: Mapped[str] = mapped_column(String(16), default=TRIGGER_DAILY)
    trigger_time: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "HH:MM"
    trigger_weekday: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=周一 .. 6=周日（weekly 用）
    trigger_interval_hours: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # interval 用

    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # 本任务跑完是否推送到用户的消息渠道（默认推）
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str] = mapped_column(String(16), default=TASK_RUN_NONE)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
