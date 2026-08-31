"""角色卡组（场景）请求/响应 schema。"""
import uuid

from pydantic import BaseModel, Field


class PersonaGroupCreate(BaseModel):
    """新建角色卡组：组名 + 2~5 个成员角色 + 可选图标/描述。"""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=2000)
    icon: str = Field(default="", max_length=16)
    member_persona_ids: list[uuid.UUID] = Field(..., min_length=2, max_length=5)


class PersonaGroupUpdate(BaseModel):
    """编辑卡组（全部可选，传啥改啥）。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=2000)
    icon: str | None = Field(default=None, max_length=16)
    member_persona_ids: list[uuid.UUID] | None = Field(
        default=None, min_length=2, max_length=5
    )
