"""轻量文本语言检测，仅用于选择 Elasticsearch 的关键词分词字段。"""
import re

LANG_ZH = "zh"
LANG_EN = "en"
LANG_MIXED = "mixed"

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def detect_text_language(text: str) -> str:
    """按中英文有效字符占比返回 zh / en / mixed。

    短文本容易被品牌名、缩写干扰，因此只有另一种语言达到至少 2 个汉字或
    2 个英文单词时才判定为 mixed。无中英文内容时返回 mixed，让调用方同时检索
    两个字段。单个英文品牌名或缩写不会把中文句子误判为 mixed。
    """
    text = text or ""
    zh_count = len(_CJK_RE.findall(text))
    en_words = _LATIN_WORD_RE.findall(text)
    en_count = sum(len(word) for word in en_words)
    total = zh_count + en_count

    if total == 0:
        return LANG_MIXED
    if zh_count == 0:
        return LANG_EN
    if en_count == 0:
        return LANG_ZH

    zh_ratio = zh_count / total
    en_ratio = en_count / total
    if zh_count >= 2 and len(en_words) >= 2:
        return LANG_MIXED
    return LANG_ZH if zh_ratio >= en_ratio else LANG_EN


def keyword_search_fields(language: str) -> list[str]:
    """返回适合该语言的 ES 多字段检索顺序。"""
    if language == LANG_ZH:
        return ["content.zh"]
    if language == LANG_EN:
        return ["content.en"]
    return ["content.zh", "content.en"]


__all__ = [
    "LANG_ZH",
    "LANG_EN",
    "LANG_MIXED",
    "detect_text_language",
    "keyword_search_fields",
]
