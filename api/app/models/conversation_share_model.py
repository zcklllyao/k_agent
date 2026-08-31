"""ConversationShare ORM 模型 —— 对话分享（快照式只读链接）。

生成分享时把当时的对话消息冻结成快照存进 snapshot，之后原对话继续聊不影响已分享内容。
凭 share_token 公开访问（无需登录），脱敏只含消息文本与图片。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class ConversationShare(Base):
    __tablename__ = "conversation_shares"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # 来源会话（会话被删不影响分享快照，故仅记录不设级联约束的强依赖）
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True
    )
    # 公开访问令牌：随机不可猜，唯一
    share_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 分享标题（取会话标题快照）
    title: Mapped[str] = mapped_column(String(256), default="对话分享")
    # 消息快照：[{role, content, images?}]，脱敏（不含工具/引用/记忆等内部细节）
    snapshot: Mapped[list] = mapped_column(JSONB, default=list)
    # 头像快照（data URL，公开页无需鉴权直接显示）：用户头像 / AI 角色头像
    user_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 是否有效（取消即置 false，保留痕迹）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # 过期时间（可空=永久）
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 浏览次数
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
