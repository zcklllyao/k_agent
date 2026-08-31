"""对话人格（角色卡）请求/响应 schema。"""
from pydantic import BaseModel, Field


class PersonaCreate(BaseModel):
    """新增人格。name 必填，其余可选。"""

    name: str = Field(min_length=1, max_length=64)
    avatar_key: str | None = Field(default=None, max_length=512)
    system_prompt: str = Field(default="", max_length=4000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class PersonaUpdate(BaseModel):
    """编辑人格（全部可选，传啥改啥）。avatar_key 传空串表示移除头像。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_key: str | None = Field(default=None, max_length=512)
    system_prompt: str | None = Field(default=None, max_length=4000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class PersonaOut(BaseModel):
    """人格出参（含头像可访问 url）。"""

    id: str
    name: str
    avatar_key: str | None
    avatar_url: str | None
    system_prompt: str
    temperature: float
    is_active: bool
