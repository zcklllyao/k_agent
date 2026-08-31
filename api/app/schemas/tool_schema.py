"""工具配置请求/响应 schema。"""
from pydantic import BaseModel


class ToolToggle(BaseModel):
    """启停某个工具。"""

    enabled: bool


class ToolItem(BaseModel):
    """工具列表项（内置工具定义 + 用户启停状态）。"""

    tool_key: str
    name: str
    description: str
    icon: str
    tool_type: str
    needs_config: bool
    config_hint: str
    enabled: bool
