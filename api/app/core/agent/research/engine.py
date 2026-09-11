"""研究编排：串起 规划 → 检索（四源）→ 分章节写作 → 汇总，产出统一事件流。

本模块是**纯异步生成器**，与传输层解耦：
- 在线发起：由 research_service 在后台任务里消费，事件经 Redis bus 广播给前端（可断线续传）。
- 定时任务（②）：将来由 Celery worker 直接消费同一引擎，无需 bus。

产出事件（dict）：
  {"type": "status", "phase": str, "detail": str}
  {"type": "plan", "title": str, "sections": [...], "queries": [...]}
  {"type": "sources", "sources": [{index,type,title,url}]}
  {"type": "section_start", "heading": str}
  {"type": "token", "text": str}
  {"type": "section_done", "heading": str}
  {"type": "report", "title": str, "markdown": str, "sources": [...]}
  {"type": "error", "message": str}
"""
import asyncio
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent.loop.controller import LoopController, RepairCallbackArgs
from app.core.agent.research.curator import curate_outline
from app.core.agent.research.distiller import distill_sources
from app.core.agent.research.models import (
    Learning,
    Source,
)
from app.core.agent.research.planner import make_plan
from app.core.agent.research.reflector import find_gap_queries
from app.core.agent.research.retriever import (
    assign_indices,
    gather_kb_sources,
    gather_mcp_sources,
    gather_web_sources,
    get_websearch_config,
)
from app.core.agent.research.writer import summarize, write_section_stream
from app.core.agent.tracing import get_tracer
from app.core.logging import get_logger

logger = get_logger(__name__)

_CITATION_RE = re.compile(r"\[来源\s*(\d+)\]")


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc or ""
    except Exception:  # noqa: BLE001
        return ""


def _linkify_citations(text: str, sources: list[Source]) -> str:
    """把正文里的 [来源N] 角标替换为带说明的可点链接。

    - 有网址的来源：渲染为 [N]，链接 title 写明「来源标题 · 域名」，悬停即可预知跳转目标。
    - 无网址的来源（知识库/工具）：保留为 [N]，title 标注其名称与类型。
    """
    meta = {s.index: s for s in sources}

    def _repl(m: re.Match) -> str:
        idx = int(m.group(1))
        s = meta.get(idx)
        if s is None:
            return f"\\[{idx}\\]"
        # markdown link title 用双引号包裹，标题里的双引号转单引号避免截断
        title = (s.title or "").replace('"', "'").strip()
        # 角标文字用的短标题（截断，避免正文过长）
        short = title[:16] + "…" if len(title) > 16 else title
        if s.url:
            dom = _domain(s.url)
            hint = f"{title} · {dom}" if dom else title
            # 链接文字直接带上来源标题，手机端无需悬停也能看懂跳转目标
            label = f"{idx} · {short}" if short else (dom or str(idx))
            return f'[\\[{label}\\]]({s.url} "{hint}")'
        # 无网址（知识库/工具）：标注来源名称，文末「参考来源」可查
        label = f"{idx} · {short}" if short else str(idx)
        return f"\\[{label}\\]"

    return _CITATION_RE.sub(_repl, text)


def _source_brief(sources: list[Source]) -> list[dict]:
    """给前端的来源简要（不含正文，避免事件过大）。"""
    return [
        {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
        for s in sources
    ]


def _build_markdown(
    title: str,
    summary: dict,
    sections: list[tuple[str, str]],
    sources: list[Source],
) -> str:
    """拼装最终报告 Markdown：标题 / TL;DR / 核心要点 / 各章节 / 参考来源。

    正文里的 [来源N] 角标会被替换为指向来源网址的可点链接（无网址的保留为 [N]）。
    """
    lines: list[str] = [f"# {title}", ""]
    tldr = (summary.get("tldr") or "").strip()
    if tldr:
        lines += [f"> {_linkify_citations(tldr, sources)}", ""]
    key_points = summary.get("key_points") or []
    if key_points:
        lines += ["## 核心要点", ""]
        lines += [f"- {_linkify_citations(p, sources)}" for p in key_points]
        lines.append("")
    for heading, content in sections:
        lines += [
            f"## {heading}",
            "",
            _linkify_citations(content.strip(), sources),
            "",
        ]
    if sources:
        lines += ["## 参考来源", ""]
        lines += [f"{s.index}. {s.cite_label()}" for s in sources]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def _pump(holder: dict, make_task) -> AsyncGenerator[dict, None]:
    """跑一个会上报进度的异步任务：边产出 progress 事件边执行，结果存进 holder['result']。

    make_task(emit) 是一个接收 emit 回调、返回结果的协程工厂。
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def _emit(ev: dict) -> None:
        await queue.put(ev)

    async def _runner() -> None:
        try:
            holder["result"] = await make_task(_emit)
        finally:
            await queue.put(None)  # 哨兵：通知 drain 结束

    task = asyncio.create_task(_runner())
    while True:
        ev = await queue.get()
        if ev is None:
            break
        yield ev
    await task


async def run_research(
    session: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None = None,
    report_id: uuid.UUID | None = None,
) -> AsyncGenerator[dict, None]:
    """执行一次深度研究（v2：规划→检索→逐源提炼→反思补搜→大纲整理→分节写作→汇总）。

    V0.0.5 ② 起末尾接入 Verifier Loop：独立 LLM-as-judge 复核 + 不合格自动 Patch / 章节重写。
    可通过 `settings.loop_enabled = False` 关闭(行为退回到 v2 原流程)。

    内部各步降级处理，尽量产出报告；引擎为纯异步生成器，与传输层解耦。

    Args:
        session: DB session(读取模型配置 + 走 Verifier Loop 时落库)
        user_id: 当前用户
        topic: 研究主题
        kb_ids: 知识库 id 过滤(None = 不限)
        report_id: 关联的 research_reports.id,Verifier Loop 用它关联 loop_runs(可选)
    """
    from app.core.llm.chat_model import (
        build_default_chat_model,
        supports_function_call,
    )

    topic = (topic or "").strip()
    tracer = get_tracer()
    async with tracer.trace(
        user_id=user_id,
        task_type="research",
        task_id=report_id,
        task_name=topic[:200] if topic else None,
    ) as tctx:
        # 给前端发个 trace_id 事件,供未来「查看执行轨迹」入口下钻
        yield {"type": "trace", "trace_id": str(tctx.trace_id)}

        try:
            model, config = await build_default_chat_model(
                session, user_id, temperature=0.4, streaming=True
            )
        except Exception as e:
            yield {"type": "error", "message": str(e)}
            return
        supports_fc = supports_function_call(config)
        ws = await get_websearch_config(session, user_id)

        # ── 1. 规划（多视角子问题）──
        yield {"type": "status", "phase": "planning", "detail": "正在规划研究提纲与多视角检索策略…"}
        async with tracer.span("规划:多视角子问题", span_type="planner") as sp:
            plan = await make_plan(model, topic)
            sp.set_attribute("section_count", len(plan.sections))
            sp.set_attribute("query_count", len(plan.queries))
        headings = [s.heading for s in plan.sections]
        yield {
            "type": "plan",
            "title": plan.title,
            "sections": [{"heading": s.heading, "points": s.points} for s in plan.sections],
            "queries": plan.queries,
        }

        # ── 检索辅助（一轮：四源并行 + 续编引用号）──
        async def _retrieve(emit, queries: list[str], start_index: int) -> list[Source]:
            async with tracer.span(
                f"检索:{len(queries)} 个角度",
                span_type="retriever",
                attributes={"k-agent.retrieval.query_count": len(queries)},
            ) as rsp:
                collected: list[Source] = []
                if ws:
                    provider, api_key = ws
                    try:
                        async with tracer.span("检索:联网", span_type="tool_call", attributes={"k-agent.tool.name": "web_search", "k-agent.tool.provider": provider}):
                            collected += await gather_web_sources(provider, api_key, queries, emit=emit)
                    except Exception as e:
                        logger.warning("研究联网检索整体失败（继续）: %s", e)
                try:
                    async with tracer.span("检索:知识库", span_type="tool_call", attributes={"k-agent.tool.name": "kb_search"}):
                        collected += await gather_kb_sources(session, user_id, queries, kb_ids, emit=emit)
                except Exception as e:
                    logger.warning("研究知识库检索整体失败（继续）: %s", e)
                try:
                    async with tracer.span("检索:MCP 增强", span_type="mcp_call", attributes={"k-agent.tool.name": "mcp_research"}):
                        collected += await gather_mcp_sources(
                            session, user_id, topic, model, supports_fc, emit=emit
                        )
                except Exception as e:
                    logger.warning("研究 MCP 增强整体失败（继续）: %s", e)
                rsp.set_payload("source_count", len(collected))
                return assign_indices(collected, start=start_index)

        # ── 2. 检索（第一轮）──
        yield {
            "type": "status",
            "phase": "searching",
            "detail": f"正在围绕 {len(plan.queries)} 个角度检索并抓取资料…",
        }
        h1: dict = {}
        async for ev in _pump(h1, lambda emit: _retrieve(emit, plan.queries, 1)):
            yield ev
        sources: list[Source] = h1.get("result") or []
        yield {"type": "sources", "sources": _source_brief(sources)}

        # ── 3. 逐源提炼（v2 核心：原始资料 → 带来源号的要点）──
        yield {
            "type": "status",
            "phase": "distilling",
            "detail": f"正在从 {len(sources)} 个来源提炼关键要点…",
        }
        h2: dict = {}
        async with tracer.span(
            f"逐源提炼:{len(sources)} 个来源",
            span_type="writer",
            attributes={"k-agent.distill.source_count": len(sources)},
        ) as dsp:
            async for ev in _pump(
                h2, lambda emit: distill_sources(model, topic, headings, sources, emit=emit)
            ):
                yield ev
            dsp.set_payload("learning_count", len(h2.get("result") or []))
        learnings: list[Learning] = h2.get("result") or []

        # ── 4. 反思补搜（找缺口 → 补一轮检索+提炼，可配关闭）──
        if settings.research_reflection_rounds > 0 and learnings:
            yield {"type": "status", "phase": "reflecting", "detail": "正在评估信息缺口…"}
            async with tracer.span("反思:找缺口子查询", span_type="planner") as fsp:
                gap_queries = await find_gap_queries(model, topic, plan.sections, learnings)
                fsp.set_payload("gap_query_count", len(gap_queries or []))
            if gap_queries:
                yield {
                    "type": "status",
                    "phase": "reflecting",
                    "detail": f"补充检索 {len(gap_queries)} 个缺口角度…",
                }
                h3: dict = {}
                async for ev in _pump(
                    h3, lambda emit: _retrieve(emit, gap_queries, len(sources) + 1)
                ):
                    yield ev
                extra_sources: list[Source] = h3.get("result") or []
                if extra_sources:
                    sources += extra_sources
                    yield {"type": "sources", "sources": _source_brief(sources)}
                    h4: dict = {}
                    async with tracer.span(
                        f"补提炼:{len(extra_sources)} 个新来源",
                        span_type="writer",
                    ):
                        async for ev in _pump(
                            h4,
                            lambda emit: distill_sources(
                                model, topic, headings, extra_sources, emit=emit
                            ),
                        ):
                            yield ev
                    learnings += h4.get("result") or []

        # 全局要点截断（按相关度），并赋全局编号供大纲整理引用
        learnings.sort(key=lambda x: x.relevance, reverse=True)
        learnings = learnings[: settings.research_max_learnings]

        # ── 5. 大纲整理（要点 → 每节核心论点 + 证据分配）──
        yield {"type": "status", "phase": "curating", "detail": "正在整理大纲、分配论据…"}
        async with tracer.span(
            "大纲整理:论点+证据分配",
            span_type="planner",
            attributes={
                "k-agent.curator.section_count": len(plan.sections),
                "k-agent.curator.learning_count": len(learnings),
            },
        ):
            curated = await curate_outline(model, topic, plan.sections, learnings)

        # ── 6. 分章节写作（吃分配的要点 + 前文摘要避免重复）──
        written: list[tuple[str, str]] = []
        failed_sections: list[str] = []
        prev_summaries: list[str] = []
        total = len(curated)
        for i, sec in enumerate(curated, 1):
            sec_learnings = [
                learnings[lid - 1] for lid in sec.learning_ids if 1 <= lid <= len(learnings)
            ]
            yield {
                "type": "status",
                "phase": "writing",
                "detail": f"正在撰写第 {i}/{total} 节：{sec.heading}",
            }
            yield {"type": "section_start", "heading": sec.heading}
            buf: list[str] = []
            async with tracer.span(
                f"写章节 {i}/{total}: {sec.heading}", span_type="writer"
            ) as wsp:
                wsp.set_attribute("section_index", i)
                wsp.set_attribute("section_total", total)
                wsp.set_attribute("learning_count", len(sec_learnings))
                try:
                    async for tok in write_section_stream(
                        model, plan.title, sec.heading, sec.thesis, sec_learnings, prev_summaries
                    ):
                        buf.append(tok)
                        yield {"type": "token", "text": tok}
                except Exception as exc:  # noqa: BLE001
                    # A single section must not discard the sections already
                    # written.  Keep a visible placeholder and continue.
                    logger.warning("章节生成异常，保留部分报告并继续：heading=%s err=%s", sec.heading, exc)
                    failed_sections.append(sec.heading)
                    if buf:
                        buf.append("\n\n> ⚠️ 本章节生成中断，以上为已生成内容。\n")
                    else:
                        buf.append("（本章节生成失败，暂无可用内容。）")
                content = "".join(buf).strip() or "（本章节暂无内容）"
                wsp.set_payload("content_chars", len(content))
            written.append((sec.heading, content))
            prev_summaries.append(f"{sec.heading}：{sec.thesis or '（见正文）'}")
            yield {"type": "section_done", "heading": sec.heading}

        # ── 7. 汇总 ──
        yield {"type": "status", "phase": "summarizing", "detail": "正在提炼摘要与核心要点…"}
        async with tracer.span("汇总:摘要与核心要点", span_type="writer"):
            body = "\n\n".join(f"## {h}\n{c}" for h, c in written)
            summary = await summarize(model, plan.title, body)

        # ── 8. 拼装 + 引用映射 ──
        markdown = _build_markdown(plan.title, summary, written, sources)
        if failed_sections:
            yield {
                "type": "quality_warning",
                "detail": "部分章节生成失败：" + "、".join(failed_sections),
                "failed_sections": failed_sections,
            }

        # ── 9. Verifier Loop(V0.0.5 ②):独立 LLM-as-judge 复核 + 不合格 Patch/Rewrite 回炉 ──
        final_markdown = markdown
        final_sources = list(sources)
        if not settings.loop_enabled:
            # 开关关闭:跳过质量复核,行为与 v2 原流程一致
            yield {
                "type": "report",
                "title": plan.title,
                "markdown": final_markdown,
                "sources": [
                    {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
                    for s in final_sources
                ],
            }
            return

        # ── 闭包内可变状态(给 callback 用,可跨多轮累加 sources/learnings 与重写章节)──
        loop_sources: list[Source] = list(sources)
        loop_learnings: list[Learning] = list(learnings)
        loop_written: list[tuple[str, str]] = list(written)
        loop_summary: dict = dict(summary or {})

        def _rebuild_artifact() -> dict[str, Any]:
            md = _build_markdown(plan.title, loop_summary, loop_written, loop_sources)
            return {
                "title": plan.title,
                "markdown": md,
                "sources": [
                    {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
                    for s in loop_sources
                ],
                "headings": [h for h, _ in loop_written],
            }

        initial_artifact = _rebuild_artifact()
        loop_status: str | None = None
        loop_note: str | None = None

        async def patch_callback(queries: list[str]) -> dict[str, Any]:
            """Patch:用 verifier 给的子查询补搜补提炼,把新要点作为「补充信息」追加到报告。"""
            try:
                new_sources = await _retrieve(None, queries, len(loop_sources) + 1)
                if not new_sources:
                    return _rebuild_artifact()
                loop_sources.extend(new_sources)
                new_learnings = await distill_sources(
                    model, topic, [h for h, _ in loop_written], new_sources, emit=None
                )
                if not new_learnings:
                    return _rebuild_artifact()
                loop_learnings.extend(new_learnings)
                # 简化合并:把新要点整理为一个「补充信息」章节追加(避免重写正文章节,成本低)
                supp_heading = "补充信息(质量复核反馈后追加)"
                supp_lines = [
                    f"- {le.text} [来源 {le.source_index}]" for le in new_learnings
                ]
                supp_content = "\n".join(supp_lines) if supp_lines else "(无补充)"
                # 替换或追加
                idx = next(
                    (i for i, (h, _) in enumerate(loop_written) if h == supp_heading), None
                )
                if idx is None:
                    loop_written.append((supp_heading, supp_content))
                else:
                    loop_written[idx] = (
                        supp_heading,
                        (loop_written[idx][1] + "\n" + supp_content).strip(),
                    )
                return _rebuild_artifact()
            except Exception as e:  # noqa: BLE001
                logger.warning("patch_callback 失败,沿用旧报告: %s", e)
                return _rebuild_artifact()

        async def rewrite_callback(chapters: list[str]) -> dict[str, Any]:
            """Rewrite:重写指定章节(用 curated thesis + 已有 learnings 重新调 writer)。"""
            try:
                heading_to_curated = {c.heading: c for c in curated}
                for ch in chapters:
                    cur = heading_to_curated.get(ch)
                    if cur is None:
                        continue
                    sec_learnings = [
                        loop_learnings[lid - 1]
                        for lid in cur.learning_ids
                        if 1 <= lid <= len(loop_learnings)
                    ]
                    buf: list[str] = []
                    async for tok in write_section_stream(
                        model, plan.title, cur.heading, cur.thesis, sec_learnings, []
                    ):
                        buf.append(tok)
                    new_content = "".join(buf).strip() or "(本章节暂无内容)"
                    idx = next(
                        (i for i, (h, _) in enumerate(loop_written) if h == ch), None
                    )
                    if idx is not None:
                        loop_written[idx] = (ch, new_content)
                return _rebuild_artifact()
            except Exception as e:  # noqa: BLE001
                logger.warning("rewrite_callback 失败,沿用旧报告: %s", e)
                return _rebuild_artifact()

        # 跑 LoopController:产出 loop_started / loop_verify_start/done / loop_repair_start/done / loop_finished 事件
        try:
            controller = LoopController(
                session=session,
                user_id=user_id,
                task_type="research",
                task_id=report_id,
                max_iterations=settings.loop_max_iterations,
            )
            async for ev in controller.run(
                topic=topic,
                initial_artifact=initial_artifact,
                verifier_kind=settings.loop_verifier_kind,
                generator_model=model,
                generator_model_name=getattr(config, "model_name", "") or "",
                repair_ctx=RepairCallbackArgs(
                    patch_callback=patch_callback,
                    rewrite_callback=rewrite_callback,
                ),
            ):
                # 拿到 loop_started.run_id 后,把 trace 关联到 LoopRun(便于报告页下钻执行轨迹)
                if ev.get("type") == "loop_started":
                    try:
                        run_id_str = ev.get("run_id")
                        if run_id_str:
                            tctx.set_loop_run_id(uuid.UUID(run_id_str))
                    except Exception:
                        pass
                if ev.get("type") == "loop_finished":
                    loop_status = ev.get("status")
                    loop_note = ev.get("note")
                    final = ev.get("final_artifact") or {}
                    final_markdown = final.get("markdown") or final_markdown
                yield ev
        except Exception as e:  # noqa: BLE001
            # Verification is advisory.  A verifier outage or an unexpected
            # repair error must not discard an otherwise usable report.
            logger.error("Verifier Loop 运行失败，发布当前报告并附质量警告：%s", e, exc_info=True)
            loop_status = "warning"
            loop_note = f"verifier 异常: {e}"

        if loop_status != "passed":
            logger.warning(
                "研究质量校验未通过，发布当前最佳版本并附警告：status=%s note=%s",
                loop_status,
                loop_note,
            )
            yield {
                "type": "quality_warning",
                "detail": loop_note or loop_status or "未返回校验结果",
            }

        yield {
            "type": "report",
            "title": plan.title,
            "markdown": final_markdown,
            "sources": [
                {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
                for s in loop_sources
            ],
        }


__all__ = ["run_research"]
