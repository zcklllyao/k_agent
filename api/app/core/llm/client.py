"""LLM 调用客户端：基于用户的模型配置调用 OpenAI 兼容接口。

封装 embedding / chat / 多模态 / rerank 调用，供解析、检索、问答复用。
对网络抖动 / 服务端 5xx / 连接中断做有限重试（指数退避），提升萃取稳定性。

V0.0.5 ③:每个对外网络调用自动包一层 `llm_call` span,记录 model + token 用量
+ 按内置单价表算 cost_cny,异步落库不阻塞主流程。tracer 关闭时 NoOp 零开销。
"""
import asyncio
import os

import httpx

from app.config import settings
from app.core.agent.tracing import get_tracer
from app.core.agent.tracing.otel_attrs import (
    GEN_AI_EMBEDDING_DIMENSIONS,
    GEN_AI_OPERATION_NAME,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_REQUEST_TEMPERATURE,
    GEN_AI_RESPONSE_FINISH_REASONS,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# 连接级重试：网络抖动/连接中断/服务端 5xx/429 时重试
_MAX_RETRIES = 3
_RETRY_BACKOFF = 1.5  # 秒，第 n 次重试等待 _RETRY_BACKOFF * n
_RETRY_STATUS = {429, 500, 502, 503, 504}

# Embedding 批量上限：阿里云 text-embedding-v3/v4 的 input 列表最多 10 条/批、每条 ≤8192 token。
# 超过则自动切片 + 并发发送，调用方无感（子块 256 token，攒满 10 条一批最划算）。
# EMBED_BATCH_SIZE / EMBED_CONCURRENCY 可经环境变量调。
_EMBED_BATCH_SIZE = max(1, int(os.getenv("EMBED_BATCH_SIZE", "10")))
_EMBED_CONCURRENCY = max(1, int(os.getenv("EMBED_CONCURRENCY", "8")))

# 进程级共享 HTTP 客户端：复用连接池，避免每次请求重建 TCP/TLS。
# 评测上万次嵌入调用时，握手开销累积可观，复用后显著提速。
_shared_client: httpx.AsyncClient | None = None
_shared_loop: asyncio.AbstractEventLoop | None = None


async def _get_shared_client() -> httpx.AsyncClient:
    """返回当前事件循环可用的客户端。

    Windows 下 Celery solo worker 的同步任务入口通常使用 asyncio.run()，
    每个任务都会创建并销毁事件循环。AsyncClient 不能跨循环复用，因此在
    检测到循环切换时丢弃旧客户端并创建新的连接池。
    """
    global _shared_client, _shared_loop
    current_loop = asyncio.get_running_loop()
    loop_changed = _shared_loop is not None and _shared_loop is not current_loop
    if _shared_client is not None and (
        _shared_client.is_closed or loop_changed or _shared_loop.is_closed()
    ):
        old_client = _shared_client
        _shared_client = None
        _shared_loop = None
        if not old_client.is_closed:
            try:
                await old_client.aclose()
            except Exception as exc:  # noqa: BLE001
                # 旧循环已经关闭时，底层连接可能无法再优雅关闭；直接丢弃即可。
                logger.debug("关闭旧 LLM HTTP 客户端失败（已丢弃）: %r", exc)
    if _shared_client is None:
        _shared_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        _shared_loop = current_loop
    return _shared_client


async def close_llm_client() -> None:
    """关闭共享 HTTP 客户端（应用/评测退出时调用）。"""
    global _shared_client, _shared_loop
    if _shared_client is not None and not _shared_client.is_closed:
        try:
            await _shared_client.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.debug("关闭共享 LLM HTTP 客户端失败（忽略）: %r", exc)
    _shared_client = None
    _shared_loop = None


async def _post_with_retry(
    url: str, *, headers: dict, json: dict, timeout: float
) -> dict:
    """带重试的 POST，返回解析后的 JSON。

    重试场景：httpx 传输异常（连接中断/读超时/对端关闭）与可重试的 HTTP 状态（429/5xx）。
    其余 4xx（如鉴权/参数错误）不重试，直接抛出。
    """
    last_exc: Exception | None = None
    client = await _get_shared_client()
    for attempt in range(_MAX_RETRIES):
        try:
            resp = await client.post(url, headers=headers, json=json, timeout=timeout)
            if resp.status_code in _RETRY_STATUS:
                raise httpx.HTTPStatusError(
                    f"可重试状态 {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            # 仅可重试状态进入重试；其余 4xx 直接抛
            if e.response is not None and e.response.status_code not in _RETRY_STATUS:
                raise
            last_exc = e
        except (httpx.TransportError, httpx.HTTPError) as e:
            # 连接中断 / 读超时 / incomplete chunked read 等传输异常
            last_exc = e
        if attempt < _MAX_RETRIES - 1:
            wait = _RETRY_BACKOFF * (attempt + 1)
            logger.warning(
                "LLM 请求失败，第 %d/%d 次重试（等待 %.1fs）: %r",
                attempt + 1, _MAX_RETRIES, wait, last_exc,
            )
            await asyncio.sleep(wait)
    raise last_exc if last_exc else RuntimeError("LLM 请求失败")


def _extract_usage(data: dict) -> tuple[int, int, int]:
    """从 OpenAI 兼容响应里提取 (input, output, cached) tokens,缺省字段返回 0。

    覆盖:
    - chat/vision: usage.prompt_tokens / completion_tokens + prompt_tokens_details.cached_tokens
    - embedding:   usage.total_tokens / prompt_tokens(把 output 置 0)
    """
    usage = data.get("usage") or {}
    input_tokens = (
        usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("total_tokens") or 0
    )
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens") or usage.get("cached_tokens") or 0
    return int(input_tokens), int(output_tokens), int(cached)


def _finish_reason(data: dict) -> list[str]:
    """从 chat/vision 响应里提取 finish_reasons(便于排查截断/工具调用结束等)。"""
    out: list[str] = []
    for ch in data.get("choices") or []:
        fr = ch.get("finish_reason")
        if fr:
            out.append(str(fr))
    return out


class LLMClient:
    """一个 provider 配置对应一个 client（base_url + api_key + model）。"""

    def __init__(self, base_url: str, api_key: str, model_name: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def embed(
        self, texts: list[str], dimensions: int | None = None
    ) -> list[list[float]]:
        """文本批量向量化。返回与输入等长的向量列表（顺序与输入一致）。

        dimensions 控制输出维度（默认取 settings.embedding_dims），
        与 ES 索引维度保持一致；支持指定维度的 provider（如智谱 embedding-3）会按此裁剪。

        超过单批上限（默认 10 条，见 EMBED_BATCH_SIZE）时自动切片 + 并发发送
        （并发数见 EMBED_CONCURRENCY），调用方无感。
        """
        if not texts:
            return []
        dims = dimensions or settings.embedding_dims
        if len(texts) <= _EMBED_BATCH_SIZE:
            return await self._embed_one_batch(texts, dims)
        batches = [texts[i:i + _EMBED_BATCH_SIZE]
                   for i in range(0, len(texts), _EMBED_BATCH_SIZE)]
        sem = asyncio.Semaphore(_EMBED_CONCURRENCY)

        async def run(idx: int, batch: list[str]):
            async with sem:
                return idx, await self._embed_one_batch(batch, dims)

        parts = await asyncio.gather(*(run(i, b) for i, b in enumerate(batches)))
        parts.sort(key=lambda x: x[0])  # 按批次顺序还原
        out: list[list[float]] = []
        for _, vecs in parts:
            out.extend(vecs)
        return out

    async def _embed_one_batch(self, texts: list[str], dims: int) -> list[list[float]]:
        """单次嵌入请求（不超过 EMBED_BATCH_SIZE 条）。"""
        payload: dict = {
            "model": self.model_name,
            "input": texts,
            "dimensions": dims,
        }
        tracer = get_tracer()
        async with tracer.llm_span(
            f"embed:{self.model_name}",
            model_name=self.model_name,
            attributes={
                GEN_AI_OPERATION_NAME: "embeddings",
                GEN_AI_REQUEST_MODEL: self.model_name,
                GEN_AI_EMBEDDING_DIMENSIONS: dims,
            },
        ) as sp:
            sp.set_payload("batch_size", len(texts))
            data = await _post_with_retry(
                f"{self.base_url}/embeddings",
                headers=self._headers, json=payload, timeout=60,
            )
            in_t, out_t, cached = _extract_usage(data)
            sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=self.model_name)
            # OpenAI 兼容：data.data[i].embedding，按 index 排序
            items = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in items]

    async def embed_one(self, text: str, dimensions: int | None = None) -> list[float]:
        vecs = await self.embed([text], dimensions=dimensions)
        return vecs[0]

    async def chat(
        self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 2048
    ) -> str:
        """非流式对话，返回完整文本。"""
        tracer = get_tracer()
        # 取最后一条 user 内容做 payload 摘要(供 trace 详情展示「请求内容」)
        last_user = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    last_user = content
                elif isinstance(content, list):
                    # 多模态消息只取文本部分摘要
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            last_user = part.get("text", "")
                            break
                break
        async with tracer.llm_span(
            f"chat:{self.model_name}",
            model_name=self.model_name,
            attributes={
                GEN_AI_OPERATION_NAME: "chat",
                GEN_AI_REQUEST_MODEL: self.model_name,
                GEN_AI_REQUEST_TEMPERATURE: temperature,
                GEN_AI_REQUEST_MAX_TOKENS: max_tokens,
            },
        ) as sp:
            sp.set_payload("messages_count", len(messages))
            if last_user:
                sp.set_payload("request_summary", last_user[:600])
            data = await _post_with_retry(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
            in_t, out_t, cached = _extract_usage(data)
            sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=self.model_name)
            reasons = _finish_reason(data)
            if reasons:
                sp.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, reasons)
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, str) and text:
                sp.set_payload("response_preview", text[:600])
            return text

    async def vision(
        self, prompt: str, image_b64: str, mime: str = "image/jpeg", max_tokens: int = 1024
    ) -> str:
        """多模态看图：传入提示词 + base64 图片，返回模型描述文本。"""
        data_url = f"data:{mime};base64,{image_b64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        tracer = get_tracer()
        async with tracer.llm_span(
            f"vision:{self.model_name}",
            model_name=self.model_name,
            attributes={
                GEN_AI_OPERATION_NAME: "chat",
                GEN_AI_REQUEST_MODEL: self.model_name,
                GEN_AI_REQUEST_MAX_TOKENS: max_tokens,
                "k-agent.vision.mime": mime,
            },
        ) as sp:
            sp.set_payload("prompt_chars", len(prompt))
            data = await _post_with_retry(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
                timeout=120,
            )
            in_t, out_t, cached = _extract_usage(data)
            sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=self.model_name)
            reasons = _finish_reason(data)
            if reasons:
                sp.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, reasons)
            return data["choices"][0]["message"]["content"]

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[tuple[int, float]]:
        """重排，返回 [(原始索引, 相关性分数), ...]，按分数降序。"""
        payload = {"model": self.model_name, "query": query, "documents": documents}
        if top_n:
            payload["top_n"] = top_n
        tracer = get_tracer()
        async with tracer.llm_span(
            f"rerank:{self.model_name}",
            model_name=self.model_name,
            attributes={
                GEN_AI_OPERATION_NAME: "rerank",
                GEN_AI_REQUEST_MODEL: self.model_name,
                "k-agent.rerank.doc_count": len(documents),
                "k-agent.rerank.top_n": top_n or len(documents),
            },
        ) as sp:
            sp.set_payload("query_chars", len(query))
            sp.set_payload("doc_count", len(documents))
            data = await _post_with_retry(
                f"{self.base_url}/rerank", headers=self._headers, json=payload, timeout=60,
            )
            # rerank 多数 provider 不返回 token usage,估算:query + 各 doc 长度 / 4 ≈ tokens
            in_t, out_t, cached = _extract_usage(data)
            if in_t == 0:
                in_t = (len(query) + sum(len(d) for d in documents)) // 4
            sp.set_tokens(input=in_t, output=out_t, cached=cached, model_name=self.model_name)
            results = data.get("results", [])
            return [
                (r["index"], r.get("relevance_score", 0.0))
                for r in sorted(
                    results, key=lambda x: x.get("relevance_score", 0.0), reverse=True
                )
            ]
