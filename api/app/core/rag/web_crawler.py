"""网页正文抓取（含 SSRF 防护）。"""
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from app.core.exceptions import BizError


def _is_safe_url(url: str) -> bool:
    """SSRF 防护：禁止访问内网/本地地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        # 解析所有 IP，任一为内网则拒绝
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


async def fetch_url_content(url: str) -> tuple[str, str]:
    """抓取网页正文，返回 (标题, 正文文本)。

    用接近真实浏览器的请求头，降低被反爬（如 Cloudflare 521/403）拦截的概率；
    瞬时错误（超时/5xx）做一次重试。
    """
    if not _is_safe_url(url):
        raise BizError("不允许访问该地址（内网/非法 URL）", code=3002)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    last_err: Exception | None = None
    html = ""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(
                timeout=20, follow_redirects=True, max_redirects=5
            ) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                html = resp.text
                break
        except httpx.HTTPError as e:
            last_err = e
            if attempt == 0:
                continue
            raise BizError(f"网页抓取失败：{e}", code=3003) from e
    if not html:
        raise BizError(f"网页抓取失败：{last_err}", code=3003)

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not extracted:
        raise BizError("未能从该网页提取到正文", code=3004)
    meta = trafilatura.extract_metadata(html)
    title = (meta.title if meta and meta.title else url)[:200]
    return title, extracted
