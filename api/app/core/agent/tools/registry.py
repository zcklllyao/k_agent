"""工具注册中心：按用户启停构建 Agent 可用的工具列表，并提供工具列表查询。

启停优先级：本轮 overrides（对话请求临时开关） > 用户 tool_configs 持久配置 > ToolSpec.default_enabled。
"""
import uuid
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.agent.tools.builtin  # noqa: F401  触发内置工具注册
from app.core.agent.tools.base import BUILTIN_REGISTRY, ToolBuildContext
from app.core.logging import get_logger
from app.repositories.tool_config_repository import ToolConfigRepository

logger = get_logger(__name__)


async def _enabled_map(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    """用户对各内置工具的启停（无记录的用默认值兜底）。"""
    rows = await ToolConfigRepository(session).list_by_user(user_id)
    user_set = {r.tool_key: r.enabled for r in rows}
    result: dict[str, bool] = {}
    for key, spec in BUILTIN_REGISTRY.items():
        result[key] = user_set.get(key, spec.default_enabled)
    return result


async def _build_builtin_tools(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None,
    stats_holder: dict[str, dict] | None,
    kb_ids: list[str] | None,
) -> list[BaseTool]:
    """只构建内置工具（知识库/记忆/联网/时间），不含 MCP。"""
    overrides = overrides or {}
    enabled = await _enabled_map(session, user_id)
    embed_holder: dict = {}
    stats_holder = stats_holder if stats_holder is not None else {}
    ctx = ToolBuildContext(
        session=session,
        user_id=user_id,
        citations=citations,
        embed_holder=embed_holder,
        stats_holder=stats_holder,
        kb_ids=kb_ids,
    )
    tools: list[BaseTool] = []
    for key, spec in BUILTIN_REGISTRY.items():
        on = overrides.get(key, enabled.get(key, spec.default_enabled))
        if not on:
            continue
        try:
            tool = await spec.builder(ctx)
            if tool is not None:  # needs_config 但未配置时 builder 返回 None
                tools.append(tool)
        except Exception as e:
            logger.warning("构建工具失败（跳过）: %s: %s", key, e)
    return tools


async def build_enabled_tools(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None = None,
    stats_holder: dict[str, dict] | None = None,
    kb_ids: list[str] | None = None,
) -> list[BaseTool]:
    """构建用户当前启用的工具列表（内置 + MCP，MCP 为无状态版本，每次调用新建连接）。

    保留给不便用上下文管理器的场景；问答生成请用 build_enabled_tools_cm（持久会话，省握手）。

    overrides: {tool_key: bool} 本轮临时开关（对话请求传入），优先级最高。
    citations: 引用收集器，传给知识库工具。
    stats_holder: 工具统计回写（按工具 key 索引），由调用方持有，orchestrator 读后用于
        填充 tool_result 事件的 stats 字段（命中数/网页数等）。
    kb_ids: 知识库检索范围（已启用检索的库 id 列表），传给知识库工具；None=不限全部库。
    """
    tools = await _build_builtin_tools(
        session, user_id, citations, overrides, stats_holder, kb_ids
    )
    # MCP 工具（⑥-B 接入，无状态版本）
    try:
        from app.core.agent.tools.mcp.loader import build_mcp_tools

        tools.extend(await build_mcp_tools(session, user_id))
    except ImportError:
        pass  # MCP 模块未就绪
    except Exception as e:
        logger.warning("构建 MCP 工具失败（忽略）: %s", e)

    return tools


@asynccontextmanager
async def build_enabled_tools_cm(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    overrides: dict[str, bool] | None = None,
    stats_holder: dict[str, dict] | None = None,
    kb_ids: list[str] | None = None,
):
    """构建启用工具（内置 + MCP）的上下文管理器版本：MCP 走「持久会话」。

    用法：
        async with build_enabled_tools_cm(...) as tools:
            ... 在此期间用 tools 跑工具编排（同一批 MCP 会话整轮复用，不重复握手）...
        # 退出时自动关闭 MCP 会话（正常/异常/取消都清理）

    MCP 模块不可用时，仅产出内置工具。
    """
    tools = await _build_builtin_tools(
        session, user_id, citations, overrides, stats_holder, kb_ids
    )
    try:
        from app.core.agent.tools.mcp.loader import open_mcp_tools
    except ImportError:
        yield tools
        return
    async with open_mcp_tools(session, user_id) as mcp_tools:
        yield [*tools, *mcp_tools]


async def list_tools_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict]:
    """工具配置页用：列出全部内置工具定义 + 用户启停状态。"""
    enabled = await _enabled_map(session, user_id)
    out: list[dict] = []
    for key, spec in BUILTIN_REGISTRY.items():
        out.append({
            "tool_key": key,
            "name": spec.name,
            "description": spec.description,
            "icon": spec.icon,
            "tool_type": "builtin",
            "needs_config": spec.needs_config,
            "config_hint": spec.config_hint,
            "enabled": enabled.get(key, spec.default_enabled),
        })
    return out


__all__ = ["build_enabled_tools", "build_enabled_tools_cm", "list_tools_for_user"]
