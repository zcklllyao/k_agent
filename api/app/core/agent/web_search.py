"""联网搜索：通过用户配置的 websearch 模型配置调用搜索 API。

provider 适配：
- qianfan：百度千帆 AI 搜索（单接口返回 references，中文友好）
- tavily：Tavily Search（国际通用，预留路径）

返回拼好的搜索结果文本，供 Agent 的联网工具使用。失败抛异常由工具层兜底。
"""
import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

QIANFAN_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/chat/completions"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def _qianfan_search(api_key: str, query: str, top_k: int = 10) -> str:
    """百度千帆 AI 搜索：返回网页 references 的 title + 正文摘要拼接。"""
    payload = {
        "messages": [{"role": "user", "content": query}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": top_k}],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(QIANFAN_SEARCH_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    refs = data.get("references", []) or []
    lines: list[str] = []
    for i, r in enumerate(refs, 1):
        title = r.get("title", "")
        content = r.get("content") or r.get("snippet") or ""
        url = r.get("url", "")
        lines.append(f"[{i}] {title}\n{content}\n来源：{url}".strip())
    return "\n\n".join(lines)


async def _tavily_search(api_key: str, query: str, top_k: int = 10) -> str:
    """Tavily 搜索：返回结果标题 + 内容摘要拼接。"""
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": top_k,
        "search_depth": "basic",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", []) or []
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(
            f"[{i}] {r.get('title', '')}\n{r.get('content', '')}\n来源：{r.get('url', '')}".strip()
        )
    return "\n\n".join(lines)


async def web_search(provider: str, api_key: str, query: str, top_k: int = 10) -> str:
    """按 provider 调用联网搜索。"""
    provider = (provider or "").lower()
    if provider == "tavily":
        return await _tavily_search(api_key, query, top_k)
    # 默认走百度千帆
    return await _qianfan_search(api_key, query, top_k)


# ── 结构化搜索：返回 [{title, url, snippet}]，供深度研究抓正文用 ──

async def _qianfan_search_structured(
    api_key: str, query: str, top_k: int
) -> list[dict]:
    payload = {
        "messages": [{"role": "user", "content": query}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": top_k}],
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(QIANFAN_SEARCH_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    out: list[dict] = []
    for r in data.get("references", []) or []:
        out.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "snippet": (r.get("content") or r.get("snippet") or "").strip(),
        })
    return out


async def _tavily_search_structured(
    api_key: str, query: str, top_k: int
) -> list[dict]:
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": top_k,
        "search_depth": "basic",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    out: list[dict] = []
    for r in data.get("results", []) or []:
        out.append({
            "title": (r.get("title") or "").strip(),
            "url": (r.get("url") or "").strip(),
            "snippet": (r.get("content") or "").strip(),
        })
    return out


async def web_search_structured(
    provider: str, api_key: str, query: str, top_k: int = 10
) -> list[dict]:
    """结构化联网搜索：返回 [{title, url, snippet}]（带 url，供抓正文）。"""
    provider = (provider or "").lower()
    if provider == "tavily":
        return await _tavily_search_structured(api_key, query, top_k)
    return await _qianfan_search_structured(api_key, query, top_k)


__all__ = ["web_search", "web_search_structured"]
