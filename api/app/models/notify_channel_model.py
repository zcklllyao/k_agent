"""NotifyChannel ORM 模型 —— PostgreSQL notify_channels 表（消息推送渠道）。

每个用户配自己的推送渠道（Server酱/企业微信/钉钉/通用 webhook），各推各的。
target（SendKey / webhook URL）用 Fernet 加密入库，接口只返回掩码。
定时任务跑完成功后，把报告 TL;DR 推到该用户所有 enabled 的渠道。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base

# 渠道类型
CHANNEL_SERVERCHAN = "serverchan"  # Server酱（个人微信推送）
CHANNEL_WECOM = "wecom"  # 企业微信群机器人
CHANNEL_DINGTALK = "dingtalk"  # 钉钉群机器人
CHANNEL_FEISHU = "feishu"  # 飞书群机器人
CHANNEL_WEBHOOK = "webhook"  # 通用 webhook（POST JSON）

CHANNEL_TYPES = {
    CHANNEL_SERVERCHAN,
    CHANNEL_WECOM,
    CHANNEL_DINGTALK,
    CHANNEL_FEISHU,
    CHANNEL_WEBHOOK,
}


class NotifyChannel(Base):
    __tablename__ = "notify_channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    channel_type: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(64), default="")  # 渠道备注名
    # SendKey / webhook URL：Fernet 加密存储
    target_encrypted: Mapped[str] = mapped_column(Text)
    # 飞书机器人签名密钥（可选；其他渠道为空），同样加密存储
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
