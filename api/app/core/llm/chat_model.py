"""LangChain ChatOpenAI 工厂：按用户的对话模型配置构建可用于 Agent 编排的 chat model。

五个 provider（openai/qwen/doubao/deepseek/zhipu）均为 OpenAI 兼容协议，
直接用 ChatOpenAI(base_url, api_key, model) 即可，无需为异构协议做动态代理。
"""
import uuid

from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.security import decrypt_secret
from app.models.model_config_model import ModelConfig
from app.repositories.model_config_repository import ModelConfigRepository

# 模型能力标记：是否支持原生 function calling（方案B 强/弱模型分流依据）
CAP_FUNCTION_CALL = "function_call"
CAP_VISION = "vision"


async def get_default_chat_config(
    session: AsyncSession, user_id: uuid.UUID
) -> ModelConfig:
    """取用户默认的对话模型配置；无则报错。"""
    configs = await ModelConfigRepository(session).list_by_user(user_id, "chat")
    if not configs:
        raise BizError("未配置对话模型，请先在模型配置中添加", code=2010)
    return next((c for c in configs if c.is_default), configs[0])


async def get_default_config_for_type(
    session: AsyncSession, user_id: uuid.UUID, type_: str, label: str
) -> ModelConfig:
    """取用户某类型的默认模型配置；无则报错。"""
    configs = await ModelConfigRepository(session).list_by_user(user_id, type_)
    if not configs:
        raise BizError(f"未配置{label}模型，请先在模型配置中添加", code=2010)
    return next((c for c in configs if c.is_default), configs[0])


def build_chat_model(
    config: ModelConfig, *, temperature: float = 0.7, streaming: bool = True
) -> ChatOpenAI:
    """按模型配置实例化 ChatOpenAI。

    `stream_usage=True`:让流式响应在最后一个 chunk 带上 usage_metadata,
    供 ③ Tracing 抽取 input/output tokens 算 cost。不开启的话流式调用没法记 token。
    """
    return ChatOpenAI(
        model=config.model_name,
        api_key=decrypt_secret(config.api_key_encrypted),
        base_url=config.base_url.rstrip("/"),
        temperature=temperature,
        streaming=streaming,
        stream_usage=True,
        # 兼容自建 OpenAI 网关偶发的连接重置/半截 SSE；研究阶段还会
        # 在关键规划请求外层再做一次退避重试。
        max_retries=4,
    )


def supports_function_call(config: ModelConfig) -> bool:
    """模型是否支持原生 function calling（按 capability 标记判断）。"""
    return CAP_FUNCTION_CALL in (config.capability or [])


async def build_default_chat_model(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    temperature: float = 0.7,
    streaming: bool = True,
) -> tuple[ChatOpenAI, ModelConfig]:
    """取默认对话配置并构建 ChatOpenAI，返回 (model, config)。"""
    config = await get_default_chat_config(session, user_id)
    model = build_chat_model(config, temperature=temperature, streaming=streaming)
    return model, config


__all__ = [
    "CAP_FUNCTION_CALL",
    "CAP_VISION",
    "get_default_chat_config",
    "get_default_config_for_type",
    "build_chat_model",
    "supports_function_call",
    "build_default_chat_model",
]
