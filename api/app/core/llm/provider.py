"""Provider 元信息与连接测试。

所有 provider 走 OpenAI 兼容协议：
- chat/multimodal/verifier：POST {base_url}/chat/completions
- embedding：POST {base_url}/embeddings
- rerank：POST {base_url}/rerank
连接测试发一个最小请求，验证 key/base_url/model 是否可用。
"""
import httpx

from app.config import settings

# 各 provider 的默认 base_url（用户可覆盖）
PROVIDER_DEFAULT_BASE_URL: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "doubao": "https://ark.cn-beijing.volces.com/api/v3",
    "deepseek": "https://api.deepseek.com",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
}


async def test_connection(
    type_: str, base_url: str, api_key: str, model_name: str
) -> tuple[bool, str]:
    """实际调一次目标 API 验证可用性。返回 (是否成功, 中文提示)。"""
    if type_ == "websearch":
        return await _test_websearch(base_url, api_key, model_name)
    if type_ == "asr":
        return _test_asr(base_url, model_name)
    base = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if type_ == "embedding":
                resp = await client.post(
                    f"{base}/embeddings",
                    headers=headers,
                    json={
                        "model": model_name,
                        "input": "ping",
                        "dimensions": settings.embedding_dims,
                    },
                )
            elif type_ == "rerank":
                resp = await client.post(
                    f"{base}/rerank",
                    headers=headers,
                    json={
                        "model": model_name,
                        "query": "ping",
                        "documents": ["doc"],
                    },
                )
            else:
                # chat / multimodal / verifier 都用 chat/completions 最小请求
                resp = await client.post(
                    f"{base}/chat/completions",
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1,
                    },
                )
    except httpx.TimeoutException:
        return False, "连接超时，请检查 base_url 是否可达"
    except httpx.RequestError as e:
        return False, f"连接失败：{e}"

    if resp.status_code == 200:
        return True, "连接成功"
    if resp.status_code in (401, 403):
        return False, "API Key 无效或无权限"
    if resp.status_code == 404:
        return False, "模型不存在或 base_url 路径错误"
    # 其它错误，尽量带上服务端返回的信息
    detail = ""
    try:
        body = resp.json()
        detail = body.get("error", {}).get("message", "") or str(body)
    except Exception:
        detail = resp.text[:200]
    return False, f"测试失败（HTTP {resp.status_code}）：{detail}"


def _test_asr(_base_url: str, model_name: str) -> tuple[bool, str]:
    """ASR 配置校验：录音文件识别是异步任务，无低成本 ping，故仅校验模型已填，
    真实可用性在发送语音时验证。"""
    if not model_name:
        return False, "请填写模型名（如 paraformer-v2 / whisper-1）"
    return True, "配置已保存（语音识别将在发送语音时验证）"


async def _test_websearch(
    provider: str, api_key: str, _model_name: str
) -> tuple[bool, str]:
    """联网搜索连接测试：用 provider（这里 base_url 字段复用存 provider 名）发一次最小搜索。"""
    from app.core.agent.web_search import web_search

    try:
        result = await web_search(provider, api_key, "今天的日期", top_k=1)
        if result:
            return True, "连接成功"
        return False, "搜索返回为空，请检查配置"
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return False, "API Key 无效或无权限"
        return False, f"测试失败（HTTP {e.response.status_code}）"
    except Exception as e:
        return False, f"连接失败：{e}"
