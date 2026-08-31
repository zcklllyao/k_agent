"""标签相关 Pydantic 模型。"""
import uuid

from pydantic import BaseModel, Field


class TagOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    doc_count: int = 0


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, max_length=16)


class TagMergeRequest(BaseModel):
    source_id: uuid.UUID  # 被合并（删除）的标签
    target_id: uuid.UUID  # 合并到的目标标签
