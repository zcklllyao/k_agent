"""情绪分析器：调用 LLM 对单段用户文本做结构化情绪分析。

产出规范化后的情绪结构（主情绪在受控词表内、维度值在合法区间）。
LLM 调用带有限重试 + json_repair 健壮解析；连续失败时返回中性兜底（不抛异常，
由 Celery 任务侧按强度阈值丢弃）。
"""
import asyncio
from dataclasses import dataclass, field

from app.core.emotion.ontology import (
    EMOTION_VOCAB,
    clamp_arousal,
    clamp_intensity,
    clamp_valence,
    normalize_emotion,
    reference_coords,
)
from app.core.emotion.prompt_renderer import render_emotion_prompt
from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

# LLM 调用失败 / 解析失败时的最大尝试次数
_MAX_ATTEMPTS = 2


@dataclass
class EmotionResult:
    emotion_type: str
    intensity: float
    valence: float
    arousal: float
    keywords: list[str] = field(default_factory=list)
    trigger: str | None = None
    summary: str | None = None


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_keywords(value) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:8]:
        s = str(item).strip()
        if s:
            out.append(s[:32])
    return out


def _neutral() -> "EmotionResult":
    return EmotionResult(emotion_type="中性", intensity=0.0, valence=0.0, arousal=0.3)


def _build_result(data: dict) -> "EmotionResult":
    """把解析出的 dict 规范化为 EmotionResult（主情绪入词表、维度 clamp、缺失兜底）。"""
    emotion = normalize_emotion(data.get("emotion_type"))
    ref_v, ref_a = reference_coords(emotion)
    intensity = clamp_intensity(_coerce_float(data.get("intensity"), 0.0))
    valence = clamp_valence(_coerce_float(data.get("valence"), ref_v))
    arousal = clamp_arousal(_coerce_float(data.get("arousal"), ref_a))

    trigger = data.get("trigger")
    trigger = trigger.strip()[:255] or None if isinstance(trigger, str) else None

    summary = data.get("summary")
    summary = summary.strip()[:500] if isinstance(summary, str) and summary.strip() else None

    return EmotionResult(
        emotion_type=emotion,
        intensity=intensity,
        valence=valence,
        arousal=arousal,
        keywords=_coerce_keywords(data.get("keywords")),
        trigger=trigger,
        summary=summary,
    )


async def analyze_emotion(client: LLMClient, text: str) -> EmotionResult:
    """分析单段用户文本的情绪。

    带有限重试：LLM 调用异常或返回无法解析时重试，连续失败返回中性兜底。
    空文本直接返回中性。
    """
    clean = (text or "").strip()
    if not clean:
        return _neutral()

    prompt = render_emotion_prompt("extract_emotion.jinja2", text=clean, vocab=EMOTION_VOCAB)
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(_MAX_ATTEMPTS):
        try:
            answer = await client.chat(messages, temperature=0.3, max_tokens=512)
        except Exception as e:
            logger.warning(
                "情绪分析 LLM 调用失败（第 %d/%d 次）: %s",
                attempt + 1,
                _MAX_ATTEMPTS,
                e,
            )
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            return _neutral()

        data = parse_json_object(answer)
        if data:
            return _build_result(data)

        logger.warning(
            "情绪分析 JSON 解析失败（第 %d/%d 次），原始片段: %s",
            attempt + 1,
            _MAX_ATTEMPTS,
            answer[:120],
        )

    return _neutral()


__all__ = ["EmotionResult", "analyze_emotion"]
