"""知识库文档相关 Pydantic 模型。"""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UrlImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=1024)
    kb_id: uuid.UUID | None = Field(default=None, description="归属知识库")


class DocumentOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_ext: str
    file_size: int
    source_type: str
    source_url: str | None
    status: str
    progress: float
    chunk_num: int
    error_msg: str | None
    tags: list[str] = []
    created_at: datetime


class DocumentListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DocumentOut]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    tags: list[str] | None = None


class BulkDeleteRequest(BaseModel):
    """批量删除文档请求；只允许一次操作有限数量，避免误操作。"""

    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class SearchHit(BaseModel):
    chunk_id: str
    content: str
    doc_name: str | None
    source_id: str | None
    source_type: str | None
    score: float
