"""MCP 服务配置相关 Pydantic 模型。"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TransportT = Literal["sse", "streamable_http"]
AuthTypeT = Literal["none", "bearer", "api_key"]


class MCPServerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    transport: TransportT = "streamable_http"
    url: str = Field(min_length=1, max_length=512)
    auth_type: AuthTypeT = "none"
    # bearer: {"token": "明文"}；api_key: {"header": "X-Api-Key", "key": "明文"}
    auth_config: dict | None = None
    enabled: bool = True


class MCPServerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    transport: TransportT | None = None
    url: str | None = Field(default=None, max_length=512)
    auth_type: AuthTypeT | None = None
    # 不传表示不改认证；传则覆盖（明文，service 负责加密）
    auth_config: dict | None = None
    enabled: bool | None = None


class MCPServerToggle(BaseModel):
    enabled: bool


class MCPToolMeta(BaseModel):
    name: str
    description: str = ""


class MCPServerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    transport: str
    url: str
    auth_type: str
    auth_masked: str  # 认证信息掩码，不返回明文
    enabled: bool
    status: str
    last_error: str | None
    tools_cache: list[MCPToolMeta] | None
    synced_at: datetime | None
    created_at: datetime


class MCPTestResult(BaseModel):
    success: bool
    message: str
    tools: list[MCPToolMeta] = Field(default_factory=list)
