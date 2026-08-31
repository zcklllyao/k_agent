"""记忆相关请求/响应 schema。"""
from pydantic import BaseModel, Field


class RememberRequest(BaseModel):
    """主动记住：用户提交一段文本让系统萃取记忆。"""

    text: str = Field(..., min_length=1, max_length=20000, description="要记住的内容")


class MemorySearchRequest(BaseModel):
    """记忆检索请求。"""

    query: str = Field(..., min_length=1, description="检索关键词")
    top_k: int = Field(default=10, ge=1, le=50)
