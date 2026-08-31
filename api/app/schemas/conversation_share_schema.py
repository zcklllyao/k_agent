"""对话分享请求/响应 schema。"""
from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    """创建分享。expire_days 为空=永久；可选 7 / 30。title 为空则用会话标题。"""

    expire_days: int | None = Field(default=None)
    title: str | None = Field(default=None, max_length=256)


class ShareOut(BaseModel):
    """分享出参（我的分享列表 / 创建返回）。"""

    id: str
    conversation_id: str
    share_token: str
    title: str
    is_active: bool
    expire_at: str | None
    view_count: int
    created_at: str | None


class SharePublicMessage(BaseModel):
    """公开页消息（脱敏）。"""

    role: str
    content: str
    images: list[str] = Field(default_factory=list)


class SharePublicOut(BaseModel):
    """公开查看出参（无需登录）。"""

    title: str
    messages: list[SharePublicMessage]
    user_avatar: str | None = None
    ai_avatar: str | None = None
    ai_name: str | None = None
    created_at: str | None
