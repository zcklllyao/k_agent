"""联网搜索工具：从互联网获取实时信息。需用户配置 websearch 模型。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.logging import get_logger

logger = get_logger(__name__)

KEY = "web_search"


class _QueryInput(BaseModel):
    query: str = Field(..., description="检索的问题或关键词")


async def _get_websearch_config(session, user_id):
    """取用户默认 websearch 配置（provider + 解密 key）；无则返回 None。"""
    from app.core.security import decrypt_secret
    from app.repositories.model_config_repository import ModelConfigRepository

    configs = await ModelConfigRepository(session).list_by_user(user_id, "websearch")
    if not configs:
        return None
    cfg = next((c for c in configs if c.is_default), configs[0])
    return cfg.provider, decrypt_secret(cfg.api_key_encrypted)


async def _build(ctx: ToolBuildContext) -> StructuredTool | None:
    ws = await _get_websearch_config(ctx.session, ctx.user_id)
    if not ws:
        # 未配置 websearch 模型 → 不构建该工具
        return None
    provider, api_key = ws
    stats_holder = ctx.stats_holder

    async def _run(query: str) -> str:
        from app.core.agent.web_search import web_search

        try:
            result = await web_search(provider, api_key, query, top_k=10)
        except Exception as e:
            logger.warning("联网搜索失败: %s", e)
            stats_holder[KEY] = {"web_count": 0, "provider": provider}
            return f"联网搜索失败：{e}"
        # 统计：按结果块数 [1] [2] ... 推断网页数；空返回则记 0
        import re

        web_count = len(re.findall(r"^\[\d+\]\s", result, re.MULTILINE)) if result else 0
        stats_holder[KEY] = {"web_count": web_count, "provider": provider}
        return f"联网搜索到以下信息：\n\n{result}" if result else "联网搜索没有返回结果。"

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description="从互联网搜索最新信息。当问题需要实时信息、最新新闻、或知识库/记忆中没有的网络资料时使用。",
        args_schema=_QueryInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="联网搜索",
        description="从互联网搜索实时信息、最新新闻。",
        icon="🌐",
        builder=_build,
        needs_config=True,
        config_hint="需先在「模型配置」添加 websearch 类型模型（百度千帆 / tavily）",
        default_enabled=False,
    )
)
