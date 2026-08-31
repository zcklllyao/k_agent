"""聊天问题路由。

知识库是用户资料的检索工具，不应成为每个普通问题的必经步骤。这里使用轻量、
可解释的规则做第一层路由：明确指向用户资料时才挂载知识库工具；需要强制检索
的场景仍由请求开关或绑定知识库的技能控制。
"""
import re


# 明确指向用户上传资料/知识库的表达。
_EXPLICIT_KB_PATTERNS = (
    r"知识库|知识库中|资料库|knowledge\s*base",
    r"上传(?:的|过的)?(?:文档|文章|资料|文件|论文|笔记)?",
    r"我(?:的|上传的|之前上传的)(?:文档|文章|资料|文件|论文|笔记)",
    r"(?:这篇|该篇|上述|以下|里面|其中).{0,8}(?:文章|文档|资料|文件|论文|笔记|内容)",
    r"(?:文章|文档|资料|文件|论文|笔记).{0,10}(?:内容|总结|概括|检索|搜索|引用|来源|数量)",
    r"(?:总结|概括|提取|检索|搜索|查找|引用).{0,12}(?:文章|文档|资料|文件|论文|笔记)",
    r"(?:多少|几).{0,6}(?:篇|份).{0,8}(?:文章|文档|资料|文件|论文|笔记)?",
    r"列出.{0,10}(?:文章|文档|资料|文件|论文|笔记)",
    r"(?:uploaded|my)\s+(?:documents?|papers?|files?|notes?)",
    r"(?:summari[sz]e|search|retrieve|cite|list).{0,20}(?:documents?|papers?|files?|notes?)",
)
_EXPLICIT_KB_RE = re.compile("|".join(f"(?:{p})" for p in _EXPLICIT_KB_PATTERNS), re.I)


def requests_knowledge_search(text: str) -> bool:
    """判断问题是否明确要求使用用户知识库/上传资料。

    这是保守的正向判断：匹配不到时返回 False，让普通问题走全局模型回答；
    用户通过界面显式打开知识库开关时不经过此函数。
    """
    query = re.sub(r"\s+", " ", (text or "").strip())
    if not query:
        return False
    return bool(_EXPLICIT_KB_RE.search(query))


__all__ = ["requests_knowledge_search"]
