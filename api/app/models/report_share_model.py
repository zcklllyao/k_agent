"""ReportShare ORM 模型 —— 深度研究报告分享（快照式只读链接）。

生成分享时把报告标题 + Markdown 正文 + 来源列表冻结进快照，原报告删改不影响已分享内容。
凭 share_token 公开访问（无需登录）。与对话分享分表：报告形态是单篇 Markdown，
和对话消息快照 [{role,content,images}] 形态差异大，独立成表更干净。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class ReportShare(Base):
    __tablename__ = "report_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 来源报告（报告被删不影响分享快照，仅记录不设强级联）
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    # 公开访问令牌：随机不可猜，唯一
    share_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), default="研究报告")
    # 报告 Markdown 正文快照
    content_md: Mapped[str] = mapped_column(Text, default="")
    # 来源列表快照：[{index,type,title,url}]
    sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
