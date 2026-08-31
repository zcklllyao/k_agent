"""把 MCPServer 配置行转成 langchain-mcp-adapters 的 connection dict。

负责：解密认证信息 → 拼 headers；SSRF 校验（禁内网地址）；按传输类型组装。
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.security import decrypt_secret
from app.models.mcp_server_model import (
    AUTH_API_KEY,
    AUTH_BEARER,
    TRANSPORT_SSE,
    MCPServer,
)

# 连接 / 读取超时（秒）
CONNECT_TIMEOUT = 15.0
SSE_READ_TIMEOUT = 60.0


def is_safe_url(url: str) -> bool:
    """SSRF 防护：仅允许 http/https 且非内网/本地地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True


def _build_headers(server: MCPServer) -> dict[str, str]:
    """按认证类型解密并拼出请求头。"""
    cfg = server.auth_config or {}
    if server.auth_type == AUTH_BEARER:
        token = cfg.get("token")
        if token:
            return {"Authorization": f"Bearer {decrypt_secret(token)}"}
    elif server.auth_type == AUTH_API_KEY:
        header_name = cfg.get("header") or "X-API-Key"
        key = cfg.get("key")
        if key:
            return {header_name: decrypt_secret(key)}
    return {}


def build_connection(server: MCPServer) -> dict:
    """MCPServer → 官方 connection dict。URL 不安全时抛 ValueError。"""
    if not is_safe_url(server.url):
        raise ValueError("不允许访问该地址（内网/非法 URL）")

    headers = _build_headers(server)
    transport = "sse" if server.transport == TRANSPORT_SSE else "streamable_http"
    conn: dict = {
        "transport": transport,
        "url": server.url,
    }
    if headers:
        conn["headers"] = headers
    if transport == "sse":
        conn["timeout"] = CONNECT_TIMEOUT
        conn["sse_read_timeout"] = SSE_READ_TIMEOUT
    return conn
