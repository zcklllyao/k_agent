"""情绪画像聚合：把最近 N 条情绪记录聚合成「当前情绪画像」。

口径（简单滚动平均）：
- avg_valence / avg_arousal：最近 N 条的算术平均。
- dominant_emotion：最近 N 条里出现次数最多的主情绪（次数相同取强度更高者）。
中性记录也纳入统计，反映真实的整体情绪基线。
"""
from collections import Counter
from dataclasses import dataclass

from app.core.emotion.ontology import DEFAULT_EMOTION
from app.models.emotion_model import EmotionRecord


@dataclass
class ProfileAgg:
    dominant_emotion: str
    avg_valence: float
    avg_arousal: float
    sample_count: int


def aggregate_profile(records: list[EmotionRecord]) -> ProfileAgg:
    """从最近若干条情绪记录聚合画像。空列表返回中性默认画像。"""
    if not records:
        return ProfileAgg(
            dominant_emotion=DEFAULT_EMOTION,
            avg_valence=0.0,
            avg_arousal=0.0,
            sample_count=0,
        )

    n = len(records)
    avg_valence = round(sum(r.valence for r in records) / n, 4)
    avg_arousal = round(sum(r.arousal for r in records) / n, 4)

    # 主导情绪：出现次数最多；并列时取累计强度更高者
    counts = Counter(r.emotion_type for r in records)
    max_count = max(counts.values())
    candidates = [e for e, c in counts.items() if c == max_count]
    if len(candidates) == 1:
        dominant = candidates[0]
    else:
        intensity_sum: dict[str, float] = {}
        for r in records:
            if r.emotion_type in candidates:
                intensity_sum[r.emotion_type] = (
                    intensity_sum.get(r.emotion_type, 0.0) + r.intensity
                )
        dominant = max(intensity_sum, key=intensity_sum.get)

    return ProfileAgg(
        dominant_emotion=dominant,
        avg_valence=avg_valence,
        avg_arousal=avg_arousal,
        sample_count=n,
    )


__all__ = ["ProfileAgg", "aggregate_profile"]
