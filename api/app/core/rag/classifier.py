"""文档/图片 AI 自动分类打标签。

策略：优先从用户已有标签中复用（语义吻合就直接用），只有都不合适才新建，
避免标签无限膨胀、产生大量近义词。标签为宽泛主题大类，最多 2 个。
"""
import json

from app.core.llm.client import LLMClient
from app.core.logging import get_logger

logger = get_logger(__name__)

_PROMPT = """你是一个内容分类助手。请阅读下面的文本，为它打 1 到 2 个宽泛的中文主题标签。

【已有标签】（请优先复用，只要语义吻合就直接选用，不要造近义词/同义词）：
{existing}

规则：
- 优先从【已有标签】中选择；只有当已有标签都明显不合适时，才创造 1 个新的宽泛标签。
- 标签必须是宽泛的主题大类（如：技术、学习、工作、财经、生活、健康、读书笔记），不是具体关键词或细分名词。
- 每个标签 2 到 6 个字，最多输出 2 个。
- 只输出 JSON 数组，形如 ["技术","学习"]，不要任何额外文字。

文本内容：
{content}
"""


async def classify_content(
    client: LLMClient, content: str, existing_tags: list[str] | None = None
) -> list[str]:
    """对内容生成分类标签（优先复用 existing_tags），返回标签名列表。

    失败返回空列表，不阻断主流程。
    """
    snippet = content[:1500]
    existing = "、".join(existing_tags) if existing_tags else "（暂无，可自行创造）"
    try:
        answer = await client.chat(
            [
                {
                    "role": "user",
                    "content": _PROMPT.format(existing=existing, content=snippet),
                }
            ],
            temperature=0.2,
            max_tokens=200,
        )
        tags = _parse_tags(answer)
        logger.info("AI 分类标签: %s（已有 %d 个）", tags, len(existing_tags or []))
        return tags
    except Exception as e:
        logger.warning("AI 分类失败（忽略）: %s", e)
        return []


def _parse_tags(answer: str) -> list[str]:
    text = answer.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        arr = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    result = []
    for t in arr:
        if isinstance(t, str) and t.strip():
            result.append(t.strip()[:16])
    return result[:2]
