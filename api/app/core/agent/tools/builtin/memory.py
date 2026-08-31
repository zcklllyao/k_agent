"""记忆检索工具：从记忆图谱召回相关实体与关系。"""
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.agent.tools.base import ToolBuildContext, ToolSpec, register_tool
from app.core.memory.retrieval.searcher import format_memory_context, search_memory

KEY = "memory_search"


class _QueryInput(BaseModel):
    query: str = Field(..., description="检索的问题或关键词")


async def _build(ctx: ToolBuildContext) -> StructuredTool:
    session = ctx.session
    user_id = ctx.user_id
    embed_holder = ctx.embed_holder
    stats_holder = ctx.stats_holder

    async def _run(query: str) -> str:
        embed_client = embed_holder.get("embedding")
        if embed_client is None:
            from app.core.llm.resolver import get_client_for_type

            embed_client = await get_client_for_type(session, user_id, "embedding")
            embed_holder["embedding"] = embed_client
        results = await search_memory(
            embed_client=embed_client, user_id=user_id, query=query, top_k=10
        )
        # 统计：实体数 + 关系数（一跳邻居关系总和）
        relation_count = sum(len(r.get("relations") or []) for r in results)
        stats_holder[KEY] = {
            "entity_count": len(results),
            "relation_count": relation_count,
        }
        if not results:
            return "没有检索到相关记忆。"
        return "检索到以下用户记忆：\n\n" + format_memory_context(results)

    return StructuredTool.from_function(
        coroutine=_run,
        name=KEY,
        description="检索关于用户本人的长期记忆（画像、偏好、关系、经历等）。当问题涉及'我'的个人信息时使用。",
        args_schema=_QueryInput,
    )


register_tool(
    ToolSpec(
        key=KEY,
        name="记忆检索",
        description="检索关于你本人的长期记忆（画像、偏好、关系、经历）。",
        icon="🧠",
        builder=_build,
        default_enabled=True,
    )
)
