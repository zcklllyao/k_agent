"""图片路由：上传 / 列表 / 详情 / 删除 / 检索 / 移动知识库。"""
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.knowledge_base_schema import MoveToKbRequest
from app.services.image_service import ImageService

router = APIRouter(prefix="/images", tags=["image"])


class ImageSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=12, ge=1, le=50)


@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    kb_id: uuid.UUID | None = Form(default=None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    service = ImageService(session)
    img = await service.upload(user.id, file.filename or "image", content, kb_id)
    return success(await service.to_out_dict(img), "上传成功，正在处理")


@router.get("")
async def list_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    tag: str | None = Query(default=None, description="按标签名筛选"),
    kb_id: uuid.UUID | None = Query(default=None, description="按知识库筛选"),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ImageService(session)
    imgs, total = await service.list_images(user.id, page, page_size, tag, kb_id)
    items = [await service.to_out_dict(i) for i in imgs]
    return success(
        {"total": total, "page": page, "page_size": page_size, "items": items}
    )


@router.post("/search")
async def search_images(
    body: ImageSearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    hits = await ImageService(session).search(user.id, body.query, body.top_k)
    return success(hits)


@router.put("/{image_id}/move")
async def move_image(
    image_id: uuid.UUID,
    body: MoveToKbRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ImageService(session)
    img = await service.move_to_kb(user.id, image_id, uuid.UUID(body.kb_id))
    return success(await service.to_out_dict(img), "已移动")


@router.get("/{image_id}")
async def get_image(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ImageService(session)
    img = await service.get_detail(user.id, image_id)
    return success(await service.to_out_dict(img))


@router.delete("/{image_id}")
async def delete_image(
    image_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ImageService(session).delete(user.id, image_id)
    return success(message="删除成功")
