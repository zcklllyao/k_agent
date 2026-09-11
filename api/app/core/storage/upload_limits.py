from fastapi import UploadFile

from app.core.exceptions import BizError


async def read_upload_limited(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload once while rejecting payloads above the configured cap."""
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise BizError(f"文件超过大小限制（最大 {max_bytes // (1024 * 1024)} MB）", code=3010)
    return content
