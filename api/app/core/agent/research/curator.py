"""大纲整理（Deep Research v2）：把零散要点组织成连贯大纲，每节配核心论点 + 证据编号。

对标 STORM/GPT Researcher 的「先整理再写」：解决分章节各写各的导致的重复/割裂/无主线。
失败时降级为「用初始提纲 + 把要点按字面相关度分配」，保证流程不中断。
"""
import asyncio
from datetime import date

from langchain_openai import ChatOpenAI

from app.core.agent.research.models import (
    CuratedSection,
    Learning,
    PlanSection,
)
from app.config import settings
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.agent.tracing import push_llm_usage
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)


def _char_bigrams(text: str) -> set[str]:
    text = "".join(ch for ch in (text or "").lower() if ch.isalnum())
    return {text[i : i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else set()


def _fallback_curate(
    sections: list[PlanSection], learnings: list[Learning]
) -> list[CuratedSection]:
    """降级：按字面 2-gram 相关度把要点分到初始章节，保证每节有料。"""
    if not sections:
        sections = [PlanSection(heading="综合分析", points="")]
    n = len(sections)
    keys = [_char_bigrams(f"{s.heading} {s.points}") for s in sections]
    buckets: list[list[int]] = [[] for _ in sections]
    for i, le in enumerate(learnings, 1):
        sig = _char_bigrams(le.text)
        # 选重叠最高的章节；都不重叠则轮转均分
        best, best_overlap = 0, -1
        for si, k in enumerate(keys):
            ov = len(k & sig)
            if ov > best_overlap:
                best_overlap, best = ov, si
        buckets[best if best_overlap > 0 else (i % n)].append(i)
    return [
        CuratedSection(heading=s.heading, thesis=s.points, learning_ids=buckets[si])
        for si, s in enumerate(sections)
    ]


async def curate_outline(
    model: ChatOpenAI,
    topic: str,
    sections: list[PlanSection],
    learnings: list[Learning],
) -> list[CuratedSection]:
    """整理大纲：LLM 把要点分配到章节并定核心论点。失败降级到字面分配。"""
    if not learnings:
        # 没要点：直接用初始提纲（写作会基于常识谨慎处理）
        return [
            CuratedSection(heading=s.heading, thesis=s.points, learning_ids=[])
            for s in (sections or [PlanSection(heading="综合分析")])
        ]

    learning_payload = [
        {"id": i, "source_index": le.source_index, "text": le.text}
        for i, le in enumerate(learnings, 1)
    ]
    prompt = render_research_prompt(
        "curate_outline.jinja2",
        topic=topic,
        sections=[{"heading": s.heading, "points": s.points} for s in sections],
        learnings=learning_payload,
        max_sections=settings.research_max_sections,
        today=date.today().isoformat(),
    )
    try:
        resp = await asyncio.wait_for(model.ainvoke(prompt), timeout=120)
        push_llm_usage(resp, model)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("大纲整理 LLM 调用失败，降级字面分配并继续：%s", e)
        return _fallback_curate(sections, learnings)

    data = parse_json_object(text) or {}
    raw_sections = data.get("sections") or []
    if not raw_sections:
        return _fallback_curate(sections, learnings)

    max_id = len(learnings)
    curated: list[CuratedSection] = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        heading = (item.get("heading") or "").strip()
        if not heading:
            continue
        ids = []
        for lid in item.get("learning_ids") or []:
            try:
                v = int(lid)
            except (TypeError, ValueError):
                continue
            if 1 <= v <= max_id:
                ids.append(v)
        curated.append(
            CuratedSection(
                heading=heading[:60],
                thesis=(item.get("thesis") or "").strip(),
                learning_ids=ids,
            )
        )
    curated = curated[: settings.research_max_sections]
    if not curated:
        return _fallback_curate(sections, learnings)
    return curated


__all__ = ["curate_outline"]
