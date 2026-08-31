"""收藏夹请求 schema。"""
from pydantic import BaseModel, Field


class FavoriteCreateRequest(BaseModel):
    target_type: str = Field(..., description="message | document | memory")
    target_id: str = Field(..., min_length=1, description="源对象 id")
    snapshot: dict | None = Field(default=None, description="标题/摘要快照，便于列表展示")
