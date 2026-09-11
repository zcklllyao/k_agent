"""基于 Redis Pub/Sub 的流式任务事件总线。

普通对话和深度研究在独立后台任务中生成内容，通过这里向 SSE 请求转发事件；同时
提供回合锁与断线续传缓冲，避免同一任务重复生成。
"""
import json
import secrets
from collections.abc import AsyncGenerator

from app.core.logging import get_logger
from app.db.redis import get_redis

logger = get_logger(__name__)

# 频道与锁沿用旧 key 前缀，避免升级时打断正在生成的任务。
_CHANNEL_PREFIX = "k-agent:stream:"
_LOCK_PREFIX = "k-agent:stream:lock:"
# AI 回合锁的最大持有时间（秒），防异常导致死锁
_LOCK_TTL = 1800
# 订阅空闲心跳间隔（秒），保活长连接，避免反向代理空闲超时断开
_PING_INTERVAL = 25


def channel_for(conv_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{conv_id}"


def _lock_key(conv_id: str) -> str:
    return f"{_LOCK_PREFIX}{conv_id}"


async def publish(conv_id: str, event: str, data: dict) -> None:
    """向任务频道广播一个事件。失败只记日志，不阻断主流程。"""
    try:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        await get_redis().publish(channel_for(conv_id), payload)
    except Exception as e:
        logger.warning("任务事件广播失败: conv=%s event=%s err=%s", conv_id, event, e)


async def open_channel(conv_id: str):
    """打开一个订阅（返回已 subscribe 的 pubsub 对象）。

    与 subscribe() 不同：本函数把「建立订阅」与「读取消息」拆开，调用方可以先 open_channel
    确保订阅就绪，再去触发会产生事件的动作，从而消除「事件早于订阅而漏收」的竞态。
    读取用 iter_channel()，结束务必 close_channel()。
    """
    pubsub = get_redis().pubsub()
    await pubsub.subscribe(channel_for(conv_id))
    return pubsub


async def iter_channel(pubsub, conv_id: str) -> AsyncGenerator[dict, None]:
    """从已打开的 pubsub 持续读取事件；空闲吐 {"event":"_ping"} 心跳保活。"""
    while True:
        try:
            raw = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_PING_INTERVAL
            )
        except Exception as e:
            logger.warning("订阅读取失败: conv=%s err=%s", conv_id, e)
            break
        if raw is None:
            yield {"event": "_ping"}
            continue
        if raw.get("type") != "message":
            continue
        data = raw.get("data")
        if not data:
            continue
        try:
            yield json.loads(data)
        except (ValueError, TypeError) as e:
            logger.warning("事件解析失败（跳过）: %s", e)


async def close_channel(pubsub, conv_id: str) -> None:
    """关闭订阅，释放资源。"""
    try:
        await pubsub.unsubscribe(channel_for(conv_id))
        await pubsub.aclose()
    except Exception as e:
        logger.warning("订阅清理失败: conv=%s err=%s", conv_id, e)


# ── 单聊流式缓冲：支持「断线重连续传」——把生成中累积的内容写 Redis，重连时补推 ──
_STREAM_BUF_PREFIX = "chatstream:buf:"
# 缓冲存活时间（秒）：覆盖一次最慢生成（含工具/多模态），过期自动清理防泄漏
_STREAM_BUF_TTL = 600


def _stream_buf_key(conv_id: str) -> str:
    return f"{_STREAM_BUF_PREFIX}{conv_id}"


async def set_stream_buffer(conv_id: str, data: dict) -> None:
    """写/刷新某会话「生成中」的累积内容（content / n / citations / tool_calls / status）。"""
    try:
        await get_redis().set(
            _stream_buf_key(conv_id),
            json.dumps(data, ensure_ascii=False),
            ex=_STREAM_BUF_TTL,
        )
    except Exception as e:
        logger.warning("写流式缓冲失败: conv=%s err=%s", conv_id, e)


async def get_stream_buffer(conv_id: str) -> dict | None:
    """读某会话的流式缓冲；无则 None。"""
    try:
        raw = await get_redis().get(_stream_buf_key(conv_id))
        if not raw:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("读流式缓冲失败: conv=%s err=%s", conv_id, e)
        return None


async def clear_stream_buffer(conv_id: str) -> None:
    try:
        await get_redis().delete(_stream_buf_key(conv_id))
    except Exception as e:
        logger.warning("清流式缓冲失败: conv=%s err=%s", conv_id, e)


async def acquire_turn_lock(conv_id: str) -> str | None:
    """尝试拿下某会话的 AI 回合锁（SET NX EX）。拿到返回 True。"""
    try:
        owner = secrets.token_urlsafe(24)
        ok = await get_redis().set(_lock_key(conv_id), owner, nx=True, ex=_LOCK_TTL)
        return owner if ok else None
    except Exception as e:
        logger.warning("获取对话回合锁失败: conv=%s err=%s", conv_id, e)
        # 拿锁失败时保守放行（宁可偶发重复也不卡死对话）
        return None


async def release_turn_lock(conv_id: str, owner: str | None) -> None:
    if not owner:
        return
    try:
        script = ("if redis.call('get', KEYS[1]) == ARGV[1] then "
                  "return redis.call('del', KEYS[1]) else return 0 end")
        await get_redis().eval(script, 1, _lock_key(conv_id), owner)
    except Exception as e:
        logger.warning("释放对话回合锁失败: conv=%s err=%s", conv_id, e)
