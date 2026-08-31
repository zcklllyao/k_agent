"""推送适配：把 (title, content) 按渠道类型组装 payload 并 POST 到目标 URL。

各渠道都是「POST 一个 JSON 到一个 URL」，无服务端鉴权，用户自配 key/url。
单次推送独立 try/except，失败返回 (False, 错误信息) 由上层记 warning 降级，不抛出。
"""
import base64
import hashlib
import hmac
import re
import time

import httpx

from app.core.logging import get_logger
from app.models.notify_channel_model import (
    CHANNEL_DINGTALK,
    CHANNEL_FEISHU,
    CHANNEL_SERVERCHAN,
    CHANNEL_WEBHOOK,
    CHANNEL_WECOM,
)

logger = get_logger(__name__)

_TIMEOUT = 10.0

# Server酱³ 的 SendKey 形如 sctp<uid>t<token>，推送域用其中的数字 uid
_SCT3_RE = re.compile(r"^sctp(\d+)t", re.IGNORECASE)


def _serverchan_url(target: str) -> str:
    """按 SendKey 形态选推送地址：

    - Server酱³（sctp<uid>t...）：https://<uid>.push.ft07.com/send/<key>.send
    - Turbo 版（SCT... 等）：https://sctapi.ftqq.com/<key>.send
    """
    key = target.strip()
    m = _SCT3_RE.match(key)
    if m:
        uid = m.group(1)
        return f"https://{uid}.push.ft07.com/send/{key}.send"
    return f"https://sctapi.ftqq.com/{key}.send"


async def push(
    channel_type: str,
    target: str,
    title: str,
    content: str,
    secret: str | None = None,
) -> tuple[bool, str]:
    """按渠道推送一条消息。返回 (是否成功, 失败原因)。

    注意：这些服务即使业务失败也常返回 HTTP 200，真正的结果在响应体里
    （Server酱 看 code、企业微信/钉钉看 errcode），故需校验响应体而非仅看状态码。
    """
    target = (target or "").strip()
    if not target:
        return False, "渠道未配置"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if channel_type == CHANNEL_SERVERCHAN:
                resp = await client.post(
                    _serverchan_url(target),
                    data={"title": title[:100], "desp": content},
                )
            elif channel_type == CHANNEL_WECOM:
                resp = await client.post(
                    target,
                    json={
                        "msgtype": "markdown",
                        "markdown": {"content": f"### {title}\n{content}"},
                    },
                )
            elif channel_type == CHANNEL_DINGTALK:
                resp = await client.post(
                    target,
                    json={
                        "msgtype": "markdown",
                        "markdown": {"title": title[:60], "text": f"### {title}\n\n{content}"},
                    },
                )
            elif channel_type == CHANNEL_FEISHU:
                # 飞书自定义机器人要求 msg_type/content 结构；启用签名安全设置时，
                # 额外携带 timestamp + HMAC-SHA256 签名（签名串为 timestamp\nsecret）。
                payload: dict[str, object] = {
                    "msg_type": "text",
                    "content": {"text": f"【k-agent】{title}\n\n{content}"},
                }
                if secret and secret.strip():
                    timestamp = str(int(time.time()))
                    string_to_sign = f"{timestamp}\n{secret.strip()}"
                    digest = hmac.new(
                        string_to_sign.encode("utf-8"),
                        digestmod=hashlib.sha256,
                    ).digest()
                    payload["timestamp"] = timestamp
                    payload["sign"] = base64.b64encode(digest).decode("ascii")
                resp = await client.post(target, json=payload)
            elif channel_type == CHANNEL_WEBHOOK:
                resp = await client.post(target, json={"title": title, "content": content})
            else:
                return False, f"未知渠道类型：{channel_type}"
        resp.raise_for_status()
        return _check_body(channel_type, resp)
    except httpx.HTTPStatusError as e:
        msg = f"HTTP {e.response.status_code}"
        logger.warning("推送失败: type=%s err=%s", channel_type, msg)
        return False, msg
    except Exception as e:  # noqa: BLE001
        logger.warning("推送失败: type=%s err=%s", channel_type, e)
        return False, str(e)


def _check_body(channel_type: str, resp: httpx.Response) -> tuple[bool, str]:
    """校验响应体业务结果（HTTP 200 不代表投递成功）。"""
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        # 非 JSON（如通用 webhook 返回纯文本）：HTTP 2xx 即认为成功
        return True, ""
    if not isinstance(body, dict):
        return True, ""
    if channel_type == CHANNEL_SERVERCHAN:
        # Server酱：{"code":0,...} 为成功；非 0 取 message
        code = body.get("code", body.get("data", {}).get("code") if isinstance(body.get("data"), dict) else 0)
        if code in (0, None):
            return True, ""
        return False, str(body.get("message") or body.get("info") or f"code={code}")
    if channel_type in (CHANNEL_WECOM, CHANNEL_DINGTALK):
        # 企业微信/钉钉：errcode 0 为成功
        errcode = body.get("errcode", 0)
        if errcode == 0:
            return True, ""
        return False, str(body.get("errmsg") or f"errcode={errcode}")
    if channel_type == CHANNEL_FEISHU:
        # 飞书机器人成功响应通常为 {"code": 0, "msg": "success"}。
        code = body.get("code", 0)
        if code in (0, None):
            return True, ""
        return False, str(body.get("msg") or body.get("message") or f"code={code}")
    return True, ""
