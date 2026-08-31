"""研究规划：用 LLM 把一句话主题拆成报告标题 + 章节提纲 + 多角度子查询。"""
import asyncio
from datetime import date

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.research.models import PlanSection, ResearchPlan
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.agent.tracing import push_llm_usage
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

MIN_SECTIONS = 3


def _fallback_plan(topic: str) -> ResearchPlan:
    """规划失败兜底：单章节 + 用主题本身作查询，保证流程不中断。"""
    return ResearchPlan(
        title=topic[:30] or "研究报告",
        sections=[
            PlanSection(
                heading="综合分析",
                points="围绕主题综合检索资料并归纳",
                sub_questions=[topic],
            )
        ],
        queries=[topic],
    )


async def make_plan(model: ChatOpenAI, topic: str) -> ResearchPlan:
    """生成研究计划（标题 + 多视角章节 + 子问题）；异常或解析失败降级兜底。"""
    topic = (topic or "").strip()
    if not topic:
        return _fallback_plan("研究报告")

    prompt = render_research_prompt(
        "plan.jinja2",
        topic=topic,
        today=date.today().isoformat(),
        min_sections=MIN_SECTIONS,
        max_sections=settings.research_max_sections,
        sub_per_section=settings.research_subquestions_per_section,
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            # Bound each planning attempt so a stalled gateway cannot consume the
            # entire research task timeout.  The retry loop below still gives a
            # transient failure a couple of chances before falling back.
            resp = await asyncio.wait_for(model.ainvoke(prompt), timeout=90)
            push_llm_usage(resp, model)
            text = resp.content if isinstance(resp.content, str) else str(resp.content)
            break
        except Exception as e:
            last_error = e
            if attempt < 2:
                wait = 1.5 * (attempt + 1)
                logger.warning(
                    "研究规划模型请求失败，第 %d/3 次重试（等待 %.1fs）：%s",
                    attempt + 1,
                    wait,
                    e,
                )
                await asyncio.sleep(wait)
            else:
                logger.error("研究规划模型连接失败：%s", e, exc_info=True)
    else:
        # Planning is an optimization, not a reason to lose the whole report.
        # A deterministic one-section plan lets retrieval/writing continue even
        # when the model gateway is temporarily unavailable or quota limited.
        logger.warning("研究规划模型连续失败，使用兜底计划继续：%s", last_error)
        return _fallback_plan(topic)

    data = parse_json_object(text)
    if not data:
        logger.warning("研究规划解析失败，用兜底计划")
        return _fallback_plan(topic)

    title = (data.get("title") or topic)[:60].strip() or topic[:30]

    sections: list[PlanSection] = []
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        heading = (item.get("heading") or "").strip()
        if not heading:
            continue
        subs = [
            q.strip()
            for q in (item.get("sub_questions") or [])
            if isinstance(q, str) and q.strip()
        ]
        sections.append(
            PlanSection(
                heading=heading[:60],
                points=(item.get("points") or "").strip(),
                sub_questions=subs,
            )
        )
    sections = sections[: settings.research_max_sections]
    if not sections:
        sections = [
            PlanSection(
                heading="综合分析", points="围绕主题综合检索资料并归纳", sub_questions=[topic]
            )
        ]

    # 扁平化全部子问题为检索查询（去重保序），供检索阶段复用。
    # 兼容旧格式：若模型仍返回顶层 queries 也并入。
    queries: list[str] = []
    seen: set[str] = set()
    for sec in sections:
        for q in sec.sub_questions:
            if q not in seen:
                seen.add(q)
                queries.append(q)
    for q in data.get("queries") or []:
        if isinstance(q, str) and q.strip() and q.strip() not in seen:
            seen.add(q.strip())
            queries.append(q.strip())
    queries = queries[: settings.research_max_queries]
    if not queries:
        queries = [topic]

    return ResearchPlan(title=title, sections=sections, queries=queries)


__all__ = ["make_plan"]
