"""本地存储文件访问：GET /api/files/{file_key}。

仅 STORAGE_BACKEND=local 时使用；OSS 后端直接返回签名 URL，不走这里。
file_key 形如 {user_id}/images/{id}.png，需带鉴权且校验归属。
"""
from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.exceptions import BizError
from app.core.storage import get_storage
from app.models.user_model import User

router = APIRouter(prefix="/files", tags=["file"])

_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
}


@router.get("/{file_key:path}")
async def get_file(file_key: str, user: User = Depends(get_current_user)):
    if settings.storage_backend.lower() != "local":
        raise BizError("当前存储后端不通过此接口访问", code=3030, status_code=400)
    # 归属校验：file_key 必须以当前用户 id 开头
    if not file_key.startswith(f"{user.id}/"):
        raise BizError("无权访问该文件", code=3031, status_code=403)
    storage = get_storage()
    if not await storage.exists(file_key):
        raise BizError("文件不存在", code=3032, status_code=404)
    content = await storage.get(file_key)
    ext = ("." + file_key.rsplit(".", 1)[-1].lower()) if "." in file_key else ""
    media_type = _MIME.get(ext, "application/octet-stream")
    return Response(content=content, media_type=media_type)
