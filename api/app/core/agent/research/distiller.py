"""逐源提炼（Deep Research v2 核心）：每个来源 → LLM 提炼成带来源号的要点 Learning。

对标 GPT Researcher：不把原始网页正文直接喂写作，而是先把每篇资料压成"针对主题的
干净要点"，既过滤噪声、又把引用对齐提前到提炼阶段（要点天然绑定 source_index）。
并发执行，单源失败跳过不影响其余。
"""
import asyncio
from datetime import date

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.research.models import Learning, Source
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.agent.tracing import push_llm_usage
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

# 提炼时给模型看的单源正文上限（再长也没必要，控 token）
_MAX_SOURCE_CHARS = 4000

# 供应商的并发限流通常不会携带可用的 Retry-After；显式退避，给前一请求释放配额的时间。
_DISTILL_RETRY_ATTEMPTS = 3
_DISTILL_RETRY_BACKOFF_SECONDS = 2.0
_DISTILL_CALL_TIMEOUT_SECONDS = 90


def _is_retryable_model_error(exc: Exception) -> bool:
    """判断提炼请求是否属于短暂的供应商限流/连接错误。"""
    message = str(exc).lower()
    markers = (
        "concurrency limit",
        "rate limit",
        "too many requests",
        "429",
        "connection error",
        "peer closed",
        "incomplete message body",
        "temporarily unavailable",
        "service unavailable",
    )
    return any(marker in message for marker in markers)


async def _invoke_with_retry(model: ChatOpenAI, prompt: str, source_index: int):
    """调用提炼模型；对并发限流等瞬态错误采用指数退避。"""
    last_error: Exception | None = None
    for attempt in range(_DISTILL_RETRY_ATTEMPTS):
        try:
            return await asyncio.wait_for(
                model.ainvoke(prompt), timeout=_DISTILL_CALL_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= _DISTILL_RETRY_ATTEMPTS - 1 or not _is_retryable_model_error(exc):
                raise
            wait = _DISTILL_RETRY_BACKOFF_SECONDS * (2**attempt)
            logger.warning(
                "提炼来源触发模型限流/瞬态错误，将在 %.1fs 后重试 (%d/%d): idx=%s err=%s",
                wait,
                attempt + 1,
                _DISTILL_RETRY_ATTEMPTS,
                source_index,
                exc,
            )
            await asyncio.sleep(wait)
    raise last_error or RuntimeError("提炼模型调用失败")


async def _distill_one(
    model: ChatOpenAI,
    topic: str,
    headings: list[str],
    source: Source,
    today: str,
) -> list[Learning]:
    """提炼单个来源 → Learning 列表。失败返回空。"""
    prompt = render_research_prompt(
        "distill.jinja2",
        topic=topic,
        headings=headings,
        source_index=source.index,
        source_title=source.title,
        source_content=(source.content or "")[:_MAX_SOURCE_CHARS],
        today=today,
    )
    try:
        resp = await _invoke_with_retry(model, prompt, source.index)
        push_llm_usage(resp, model)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("提炼来源失败（跳过）: idx=%s err=%s", source.index, e)
        raise RuntimeError(f"来源 {source.index} 提炼模型连接失败：{e}") from e

    data = parse_json_object(text) or {}
    out: list[Learning] = []
    for item in data.get("learnings") or []:
        if not isinstance(item, dict):
            continue
        t = (item.get("text") or "").strip()
        if not t:
            continue
        try:
            rel = float(item.get("relevance", 0.5))
        except (TypeError, ValueError):
            rel = 0.5
        out.append(
            Learning(
                text=t,
                source_index=source.index,
                date_hint=(item.get("date_hint") or "").strip(),
                relevance=max(0.0, min(1.0, rel)),
            )
        )
    return out


async def distill_sources(
    model: ChatOpenAI,
    topic: str,
    headings: list[str],
    sources: list[Source],
    emit=None,
) -> list[Learning]:
    """并发提炼全部来源，按相关度过滤 + 截断到上限。

    emit: 可选异步回调，逐源完成时上报进度。
    """
    if not sources:
        return []
    today = date.today().isoformat()
    sem = asyncio.Semaphore(max(1, settings.research_distill_concurrency))
    done = 0
    total = len(sources)

    async def _run(src: Source) -> list[Learning]:
        nonlocal done
        try:
            async with sem:
                res = await _distill_one(model, topic, headings, src, today)
            ok = True
        except Exception as exc:  # noqa: BLE001
            # 单个来源失败不应让整份研究失败；其余来源仍可支撑报告。
            logger.warning("提炼来源失败，跳过并继续: idx=%s err=%s", src.index, exc)
            res = []
            ok = False
        done += 1
        if emit is not None:
            try:
                await emit(
                    {
                        "type": "progress",
                        "icon": "distill",
                        "ok": ok,
                        "text": (
                            f"已提炼 {done}/{total}：{src.title[:30]}（{len(res)} 条要点）"
                            if ok
                            else f"来源 {done}/{total} 提炼暂时失败，已跳过：{src.title[:30]}"
                        ),
                    }
                )
            except Exception:  # noqa: BLE001
                pass
        return res

    results = await asyncio.gather(*[_run(s) for s in sources])
    learnings: list[Learning] = []
    for r in results:
        learnings.extend(r)

    # 相关度过滤 + 按相关度排序 + 截断上限
    learnings = [le for le in learnings if le.relevance >= settings.research_relevance_min]
    learnings.sort(key=lambda x: x.relevance, reverse=True)
    return learnings[: settings.research_max_learnings]


__all__ = ["distill_sources"]
