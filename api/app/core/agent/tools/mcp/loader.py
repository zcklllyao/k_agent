"""MCP 工具加载：基于官方 langchain-mcp-adapters 把外部 MCP server 工具转成 LangChain 工具。

- build_mcp_tools：问答时调用，读已启用 server → 加载其工具，工具名清洗+加 server 前缀+去重。
- fetch_tools_meta：test/sync 时调用，连单个 server 拉工具清单（原始 name/description）。
单个 server 失败降级跳过，不影响其余 server 与内置工具。

多 server 并行加载 + 单 server 超时，避免串行握手和挂死节点拖慢首包。

工具名约束：OpenAI function calling 要求工具名匹配 ^[a-zA-Z0-9_-]+$ 且不超过 64 字符，
故对 server 名与 MCP 原始工具名统一清洗（非法字符替换为 _），并去重。
"""
import asyncio
import re
import time
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.tools.mcp.connection import CONNECT_TIMEOUT, build_connection
from app.core.logging import get_logger
from app.models.mcp_server_model import MCPServer
from app.repositories.mcp_server_repository import MCPServerRepository

logger = get_logger(__name__)

_INVALID = re.compile(r"[^a-zA-Z0-9_-]")
_MAX_NAME_LEN = 64

# 进程内 MCP 工具缓存：避免每轮对话都重连 server 拉工具清单（握手+协商耗时）。
# key=user_id，value=(过期时间戳, server 指纹, 工具列表)。指纹变化（增删/改 server）即失效。
_MCP_CACHE: dict[str, tuple[float, str, list[BaseTool]]] = {}
_MCP_CACHE_TTL = 300.0  # 秒

# 单个 server 拉工具清单的超时：并行后总等待≈最慢那个，挂死节点最多拖这么久
_MCP_LOAD_TIMEOUT = min(CONNECT_TIMEOUT, 8.0)


def _servers_fingerprint(servers: list[MCPServer]) -> str:
    """已启用 server 的指纹：id + updated_at，任一变化即缓存失效。"""
    parts = [
        f"{s.id}:{s.updated_at.isoformat() if s.updated_at else ''}"
        for s in servers
    ]
    return "|".join(sorted(parts))


def _sanitize(text: str) -> str:
    """清洗为合法工具名片段：非法字符→_，去首尾下划线；空则回退 'mcp'。"""
    cleaned = _INVALID.sub("_", text).strip("_")
    return cleaned or "mcp"


async def _load_raw_tools(server: MCPServer) -> list[BaseTool]:
    """连接单个 server 加载原始工具（不改名）。"""
    conn = build_connection(server)
    return await load_mcp_tools(None, connection=conn)


async def _load_raw_tools_timed(server: MCPServer) -> list[BaseTool]:
    """带超时的单 server 加载，超时/失败向上抛，由 gather 汇总。"""
    return await asyncio.wait_for(_load_raw_tools(server), timeout=_MCP_LOAD_TIMEOUT)


def _rename(tool: BaseTool, prefix: str, seen: set[str]) -> None:
    """把工具名清洗为合法名（{prefix}__{tool}），并在 seen 内去重。"""
    base = f"{prefix}__{_sanitize(tool.name)}"[:_MAX_NAME_LEN]
    name = base
    i = 1
    while name in seen:
        suffix = f"_{i}"
        name = base[: _MAX_NAME_LEN - len(suffix)] + suffix
        i += 1
    seen.add(name)
    tool.name = name


def _collect_renamed(
    items: list[tuple[MCPServer, list[BaseTool]]],
) -> list[BaseTool]:
    """按 server 顺序清洗工具名并合并。"""
    tools: list[BaseTool] = []
    seen: set[str] = set()
    for server, raw in items:
        prefix = _sanitize(server.name)
        for t in raw:
            _rename(t, prefix, seen)
            tools.append(t)
    return tools


async def build_mcp_tools(
    session: AsyncSession, user_id: uuid.UUID
) -> list[BaseTool]:
    """构建该用户所有已启用 MCP server 的工具列表（名称清洗+去重）。

    多 server 并行加载；单 server 超时/失败跳过。
    带进程内 TTL 缓存：全部成功且指纹未变时复用，避免每轮重连握手。
    """
    servers = await MCPServerRepository(session).list_by_user(
        user_id, enabled_only=True
    )
    if not servers:
        return []

    uid = str(user_id)
    fingerprint = _servers_fingerprint(servers)
    now = time.monotonic()
    cached = _MCP_CACHE.get(uid)
    if cached and cached[0] > now and cached[1] == fingerprint:
        return list(cached[2])  # 复用缓存（返回副本，避免外部改名污染缓存）

    started = time.monotonic()
    results = await asyncio.gather(
        *[_load_raw_tools_timed(s) for s in servers],
        return_exceptions=True,
    )

    ok_items: list[tuple[MCPServer, list[BaseTool]]] = []
    for server, result in zip(servers, results, strict=True):
        if isinstance(result, BaseException):
            err = (
                f"超时(>{_MCP_LOAD_TIMEOUT:.0f}s)"
                if isinstance(result, TimeoutError)
                else result
            )
            logger.warning("加载 MCP 工具失败（跳过）: %s: %s", server.name, err)
            continue
        ok_items.append((server, result))

    tools = _collect_renamed(ok_items)
    elapsed = time.monotonic() - started
    logger.info(
        "MCP 工具并行加载完成: user=%s servers=%d ok=%d fail=%d tools=%d elapsed=%.2fs",
        uid,
        len(servers),
        len(ok_items),
        len(servers) - len(ok_items),
        len(tools),
        elapsed,
    )

    # 成功子集也缓存：否则像 stock 这种常挂节点会让「had_failure」每轮都为真，
    # 缓存永远写不进去，每条消息都要重新握手（常见多等 5~8 秒）。
    # 指纹随 server 配置变化失效；坏节点在 TTL 内不重试，可在工具页关掉或等缓存过期。
    _MCP_CACHE[uid] = (now + _MCP_CACHE_TTL, fingerprint, list(tools))
    return tools


async def _open_one_server(
    server: MCPServer,
) -> tuple[AsyncExitStack, MCPServer, list[BaseTool]] | None:
    """并行打开单个 server 的持久会话；失败返回 None 并自行清理。"""
    local = AsyncExitStack()
    try:
        conn = build_connection(server)
        client = MultiServerMCPClient({str(server.id): conn})
        mcp_session = await asyncio.wait_for(
            local.enter_async_context(client.session(str(server.id))),
            timeout=_MCP_LOAD_TIMEOUT,
        )
        raw = await asyncio.wait_for(
            load_mcp_tools(mcp_session), timeout=_MCP_LOAD_TIMEOUT
        )
        return local, server, raw
    except Exception as e:
        err = (
            f"超时(>{_MCP_LOAD_TIMEOUT:.0f}s)"
            if isinstance(e, TimeoutError)
            else e
        )
        logger.warning("打开 MCP 会话失败（跳过）: %s: %s", server.name, err)
        try:
            await local.aclose()
        except Exception as close_err:  # noqa: BLE001
            logger.warning("关闭失败的 MCP 会话出错（忽略）: %s", close_err)
        return None


@asynccontextmanager
async def open_mcp_tools(session: AsyncSession, user_id: uuid.UUID):
    """打开该用户所有已启用 MCP server 的「持久会话」并产出工具（上下文管理器）。

    与 build_mcp_tools 的区别：build_mcp_tools 产出的工具每次调用都新建连接+握手；
    本函数对每个 server 开一条**活着的 ClientSession**（整段 with 期间保持），其工具的
    每次调用都复用这条会话，不再重复握手——大幅降低多次工具调用的累计延迟。

    多 server 并行开会话；单个失败跳过。退出时统一关闭。
    """
    servers = await MCPServerRepository(session).list_by_user(
        user_id, enabled_only=True
    )
    stack = AsyncExitStack()
    await stack.__aenter__()
    try:
        opened: list[tuple[AsyncExitStack, MCPServer, list[BaseTool]]] = []
        if servers:
            started = time.monotonic()
            results = await asyncio.gather(
                *[_open_one_server(s) for s in servers],
            )
            for item in results:
                if item is None:
                    continue
                local, server, raw = item
                # 把子 stack 的清理挂到父 stack，with 结束时一并关闭
                stack.push_async_callback(local.aclose)
                opened.append((local, server, raw))
            logger.info(
                "MCP 持久会话并行打开完成: user=%s servers=%d ok=%d elapsed=%.2fs",
                user_id,
                len(servers),
                len(opened),
                time.monotonic() - started,
            )

        tools = _collect_renamed([(s, raw) for _, s, raw in opened])
        yield tools
    finally:
        try:
            await stack.aclose()
        except Exception as e:  # noqa: BLE001
            logger.warning("关闭 MCP 会话出错（忽略）: %s", e)


def invalidate_mcp_cache(user_id: uuid.UUID | str | None = None) -> None:
    """清除 MCP 工具缓存（增删/改 server 或测试连接后调用）。None=全部清。"""
    if user_id is None:
        _MCP_CACHE.clear()
    else:
        _MCP_CACHE.pop(str(user_id), None)


async def fetch_tools_meta(server: MCPServer) -> list[dict]:
    """连接 server 拉取工具清单元信息（原始名，用于测试连接 / 同步）。

    抛出异常由调用方捕获并记入 server.last_error。
    """
    tools = await _load_raw_tools_timed(server)
    return [
        {"name": t.name, "description": (t.description or "")[:500]}
        for t in tools
    ]


__all__ = ["build_mcp_tools", "open_mcp_tools", "fetch_tools_meta", "invalidate_mcp_cache"]
