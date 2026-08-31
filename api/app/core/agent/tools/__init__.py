"""Agent 工具系统：内置工具注册中心 + 按用户启停构建可用工具。

- base：ToolSpec 定义 + 注册表 + 构建上下文
- builtin/：各内置工具（知识库/记忆/联网/时间），import 时自注册
- registry：build_enabled_tools（问答用）+ list_tools_for_user（配置页用）
"""
from app.core.agent.tools.registry import (
    build_enabled_tools,
    build_enabled_tools_cm,
    list_tools_for_user,
)

__all__ = ["build_enabled_tools", "build_enabled_tools_cm", "list_tools_for_user"]
