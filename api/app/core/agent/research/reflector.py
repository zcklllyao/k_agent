"""反思补搜（Deep Research v2）：看大纲 + 已提炼要点，找信息缺口 → 生成补充查询。

有界（默认 1 轮，可配 0 关闭），让"搜不好整篇废"的线性流程有一次自我纠正机会。
"""
from datetime import date

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.research.models import Learning, PlanSection
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.agent.tracing import push_llm_usage
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

# 喂给缺口分析的要点条数上限（控 token）
_MAX_LEARNINGS_PREVIEW = 40


async def find_gap_queries(
    model: ChatOpenAI,
    topic: str,
    sections: list[PlanSection],
    learnings: list[Learning],
) -> list[str]:
    """分析信息缺口，产出补充检索查询；无缺口或失败返回空列表。"""
    headings = [f"{s.heading}：{s.points}" for s in sections]
    preview = [le.text for le in learnings[:_MAX_LEARNINGS_PREVIEW]]
    prompt = render_research_prompt(
        "gap_check.jinja2",
        topic=topic,
        headings=headings,
        learnings=preview,
        max_queries=settings.research_reflection_max_queries,
        today=date.today().isoformat(),
    )
    try:
        resp = await model.ainvoke(prompt)
        push_llm_usage(resp, model)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("反思缺口分析失败（跳过补搜）: %s", e)
        return []

    data = parse_json_object(text) or {}
    out: list[str] = []
    seen: set[str] = set()
    for q in data.get("queries") or []:
        if isinstance(q, str) and q.strip() and q.strip() not in seen:
            seen.add(q.strip())
            out.append(q.strip())
    return out[: settings.research_reflection_max_queries]


__all__ = ["find_gap_queries"]
