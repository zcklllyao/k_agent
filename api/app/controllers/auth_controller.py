"""鉴权路由：注册 / 登录 / 刷新 / 退出 / 当前用户 / 改密 / 头像。"""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.core.storage import get_storage
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.auth_schema import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UpdateProfileRequest,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> dict:
    """用户输出：把头像 file_key 转成可访问 URL。"""
    data = UserOut.model_validate(user).model_dump(mode="json")
    if user.avatar:
        data["avatar"] = get_storage().get_url(user.avatar)
    return data


@router.post("/register")
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = await AuthService(session).register(body.username, body.password)
    return success(UserOut.model_validate(user).model_dump(mode="json"), "注册成功")


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    user = await service.authenticate(body.username, body.password)
    access, refresh = service.issue_tokens(user)
    return success(
        TokenPair(access_token=access, refresh_token=refresh).model_dump(), "登录成功"
    )


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    access, refresh_token = await AuthService(session).refresh(body.refresh_token)
    return success(
        TokenPair(access_token=access, refresh_token=refresh_token).model_dump()
    )


@router.post("/logout")
async def logout(_: User = Depends(get_current_user)):
    # 无状态 JWT：登出由前端清除 token 实现，这里仅作语义端点
    return success(message="已退出登录")


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return success(_user_out(user))


@router.put("/profile")
async def update_profile(
    body: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    updated = await AuthService(session).update_nickname(user, body.nickname)
    return success(_user_out(updated), "资料已更新")


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await AuthService(session).change_password(
        user, body.old_password, body.new_password
    )
    return success(message="密码修改成功")


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    updated = await AuthService(session).update_avatar(
        user, file.filename or "avatar.png", content
    )
    return success(_user_out(updated), "头像更新成功")
