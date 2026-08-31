"""工具系统基础：内置工具定义（ToolSpec）与注册表。

内置工具的「定义」在代码里用 ToolSpec 声明并注册到 BUILTIN_REGISTRY；
用户对工具的「启停」存在 tool_configs 表。问答时按用户启停 + 本轮覆盖构建工具列表。
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from langchain_core.tools import StructuredTool

# 工具类型
TOOL_TYPE_BUILTIN = "builtin"
TOOL_TYPE_MCP = "mcp"


@dataclass
class ToolBuildContext:
    """构建工具时的上下文（传给 builder）。"""

    session: object  # AsyncSession（避免循环导入用 object 标注）
    user_id: object  # uuid.UUID
    citations: list[dict]  # 引用收集器（知识库工具写入）
    embed_holder: dict  # embedding client 缓存（记忆工具复用）
    # 工具统计回写（按工具 key 索引最近一次执行的统计：命中数 / 实体数 / 网页数 等）。
    # orchestrator 在产 tool_result 事件时读取并清空，前端 chip 副文绑定。
    stats_holder: dict[str, dict]
    # 知识库检索范围：本轮启用检索的知识库 id 列表；None=不限（全部库）。
    kb_ids: list[str] | None = None


# builder 签名：异步，返回一个 StructuredTool 或 None（无法构建则跳过）
BuilderFn = Callable[[ToolBuildContext], Awaitable[StructuredTool | None]]


@dataclass
class ToolSpec:
    """内置工具定义。"""

    key: str  # 唯一标识，如 "knowledge_search" / "datetime"
    name: str  # 中文展示名
    description: str  # 给用户看的说明（工具配置页）
    icon: str  # 前端图标（emoji）
    builder: BuilderFn  # 构建 StructuredTool 的异步函数
    needs_config: bool = False  # 是否需要额外配置（如联网需 websearch 模型）
    config_hint: str = ""  # 需要配置时的提示文案
    default_enabled: bool = True  # 默认是否启用


# 内置工具注册表：key -> ToolSpec
BUILTIN_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    """注册一个内置工具。"""
    BUILTIN_REGISTRY[spec.key] = spec
    return spec


__all__ = [
    "TOOL_TYPE_BUILTIN",
    "TOOL_TYPE_MCP",
    "ToolBuildContext",
    "ToolSpec",
    "BUILTIN_REGISTRY",
    "register_tool",
]
