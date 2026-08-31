from app.core.rag.language import (
    LANG_EN,
    LANG_MIXED,
    LANG_ZH,
    detect_text_language,
    keyword_search_fields,
)


def test_detect_chinese() -> None:
    assert detect_text_language("这是一个中文知识库文档。") == LANG_ZH


def test_detect_english() -> None:
    assert detect_text_language("This is an English knowledge base document.") == LANG_EN


def test_detect_mixed_language() -> None:
    assert detect_text_language("这个 API returns user profile data") == LANG_MIXED


def test_short_foreign_terms_do_not_flip_language() -> None:
    assert detect_text_language("使用 k-agent 上传中文文档") == LANG_ZH
    assert detect_text_language("k-agent supports 文档 upload and search") == LANG_MIXED


def test_keyword_search_fields() -> None:
    assert keyword_search_fields(LANG_ZH) == ["content.zh"]
    assert keyword_search_fields(LANG_EN) == ["content.en"]
    assert keyword_search_fields(LANG_MIXED) == ["content.zh", "content.en"]
