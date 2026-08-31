"""深度研究请求 schema。"""
import uuid

from pydantic import BaseModel, Field


class ResearchStartRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000, description="一句话研究需求")
    # 检索范围：指定知识库 id 列表；为空则用用户「已启用检索」的库集合
    kb_ids: list[str] | None = None


class SaveToKbRequest(BaseModel):
    kb_id: uuid.UUID | None = None  # 存入哪个知识库；不传落默认库


class OptimizeTopicRequest(BaseModel):
    """研究指令一键润色请求（深度研究主题 + 定时任务研究指令共用）。"""

    topic: str = Field(..., min_length=1, max_length=2000, description="待润色的研究指令")
