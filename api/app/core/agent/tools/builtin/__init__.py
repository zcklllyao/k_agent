"""导入各内置工具模块，触发其 register_tool 注册到 BUILTIN_REGISTRY。"""
from app.core.agent.tools.builtin import (  # noqa: F401
    datetime_tool,
    knowledge,
    memory,
    schedule,
    web_search,
)
