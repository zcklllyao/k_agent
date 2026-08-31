"""情绪受控词表：离散主情绪 + Russell 情绪环（valence-arousal）参考坐标。

valence（效价）：-1 极消极 ~ +1 极积极
arousal（唤醒度）：0 极平静 ~ 1 极激动

参考坐标用于：①给 LLM 抽取时的锚定参考；②LLM 未给维度值时按主情绪兜底填充；
③校验 LLM 给的维度值是否与主情绪大致一致（偏差过大时以词表为准，防幻觉）。
"""

# 主情绪受控词表：emotion_type -> (定义, 参考 valence, 参考 arousal)
EMOTION_VOCAB: dict[str, tuple[str, float, float]] = {
    "喜悦": ("开心、愉快、满足、兴奋的积极情绪", 0.8, 0.7),
    "平静": ("放松、安宁、中性平和的状态", 0.2, 0.2),
    "期待": ("对未来抱有积极的盼望、憧憬", 0.6, 0.6),
    "感动": ("被触动、温暖、感激的情绪", 0.7, 0.5),
    "悲伤": ("难过、失落、沮丧、低落", -0.7, 0.3),
    "愤怒": ("生气、恼火、不满、被冒犯", -0.6, 0.8),
    "恐惧": ("害怕、担忧、不安、惊慌", -0.6, 0.7),
    "焦虑": ("紧张、压力、忐忑、心神不宁", -0.5, 0.7),
    "疲惫": ("劳累、倦怠、精力耗尽", -0.3, 0.2),
    "厌恶": ("反感、嫌恶、排斥", -0.7, 0.5),
    "惊讶": ("意外、震惊、出乎意料（中性偏激动）", 0.1, 0.8),
    "孤独": ("寂寞、被孤立、缺乏陪伴的失落", -0.5, 0.3),
    "中性": ("无明显情绪倾向", 0.0, 0.3),
}

# 默认情绪（无法判断或弱情绪时）
DEFAULT_EMOTION = "中性"


def is_valid_emotion(emotion: str) -> bool:
    return emotion in EMOTION_VOCAB


def reference_coords(emotion: str) -> tuple[float, float]:
    """取某主情绪的参考 (valence, arousal)；未知情绪回退中性。"""
    info = EMOTION_VOCAB.get(emotion) or EMOTION_VOCAB[DEFAULT_EMOTION]
    return info[1], info[2]


def normalize_emotion(emotion: str | None) -> str:
    """规范主情绪到受控词表；不在表内的回退默认情绪。"""
    if emotion and emotion.strip() in EMOTION_VOCAB:
        return emotion.strip()
    return DEFAULT_EMOTION


def clamp_valence(v: float) -> float:
    return max(-1.0, min(1.0, v))


def clamp_arousal(a: float) -> float:
    return max(0.0, min(1.0, a))


def clamp_intensity(i: float) -> float:
    return max(0.0, min(1.0, i))


__all__ = [
    "EMOTION_VOCAB",
    "DEFAULT_EMOTION",
    "is_valid_emotion",
    "reference_coords",
    "normalize_emotion",
    "clamp_valence",
    "clamp_arousal",
    "clamp_intensity",
]
