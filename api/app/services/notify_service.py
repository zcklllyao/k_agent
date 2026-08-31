"""消息推送业务服务：渠道 CRUD（key 加密/掩码）+ 测试推送 + 给用户推送。

target（SendKey/URL）用 Fernet 加密入库，接口只返回掩码；推送时解密后调 pusher。
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.notify import pusher
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.notify_channel_model import NotifyChannel
from app.repositories.notify_channel_repository import NotifyChannelRepository
from app.schemas.notify_schema import NotifyChannelCreate, NotifyChannelUpdate

logger = get_logger(__name__)


class NotifyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotifyChannelRepository(session)

    async def create(
        self, user_id: uuid.UUID, body: NotifyChannelCreate
    ) -> NotifyChannel:
        ch = NotifyChannel(
            user_id=user_id,
            channel_type=body.channel_type,
            name=body.name.strip(),
            target_encrypted=encrypt_secret(body.target.strip()),
            secret_encrypted=(
                encrypt_secret(body.secret.strip())
                if body.secret and body.secret.strip()
                else None
            ),
            enabled=body.enabled,
        )
        created = await self.repo.add(ch)
        logger.info("创建推送渠道: user=%s id=%s type=%s", user_id, created.id, body.channel_type)
        return created

    async def update(
        self, user_id: uuid.UUID, ch_id: uuid.UUID, body: NotifyChannelUpdate
    ) -> NotifyChannel:
        ch = await self._get_or_404(user_id, ch_id)
        if body.name is not None:
            ch.name = body.name.strip()
        if body.target is not None and body.target.strip():
            ch.target_encrypted = encrypt_secret(body.target.strip())
        if body.secret is not None:
            ch.secret_encrypted = (
                encrypt_secret(body.secret.strip()) if body.secret.strip() else None
            )
        if body.enabled is not None:
            ch.enabled = body.enabled
        return await self.repo.save(ch)

    async def delete(self, user_id: uuid.UUID, ch_id: uuid.UUID) -> None:
        ch = await self._get_or_404(user_id, ch_id)
        await self.repo.delete(ch)

    async def list_channels(self, user_id: uuid.UUID) -> list[dict]:
        chs = await self.repo.list_by_user(user_id)
        return [self.to_dict(c) for c in chs]

    async def test_push(self, user_id: uuid.UUID, ch_id: uuid.UUID) -> None:
        """对某渠道发一条测试消息。失败抛 BizError 让前端看到原因。"""
        ch = await self._get_or_404(user_id, ch_id)
        target = decrypt_secret(ch.target_encrypted)
        secret = decrypt_secret(ch.secret_encrypted) if ch.secret_encrypted else None
        ok, err = await pusher.push(
            ch.channel_type,
            target,
            "k-agent 测试推送",
            "如果你收到这条消息，说明推送渠道配置成功 🎉",
            secret=secret,
        )
        if not ok:
            raise BizError(f"推送失败：{err}", code=3080)

    async def push_to_user(
        self,
        user_id: uuid.UUID,
        title: str,
        content: str,
        channel_type: str | None = None,
    ) -> int:
        """给用户所有已启用渠道推送一条消息（用于定时任务完成通知）。

        返回成功推送的渠道数。单渠道失败记 warning 跳过，不影响整体。
        """
        channels = await self.repo.list_enabled(user_id)
        if channel_type:
            channels = [ch for ch in channels if ch.channel_type == channel_type]
        sent = 0
        for ch in channels:
            try:
                target = decrypt_secret(ch.target_encrypted)
                secret = decrypt_secret(ch.secret_encrypted) if ch.secret_encrypted else None
                ok, err = await pusher.push(
                    ch.channel_type, target, title, content, secret=secret
                )
                if ok:
                    sent += 1
                else:
                    logger.warning("渠道推送失败（跳过）: id=%s err=%s", ch.id, err)
            except Exception as e:  # noqa: BLE001
                logger.warning("渠道推送异常（跳过）: id=%s err=%s", ch.id, e)
        return sent

    async def _get_or_404(
        self, user_id: uuid.UUID, ch_id: uuid.UUID
    ) -> NotifyChannel:
        ch = await self.repo.get(user_id, ch_id)
        if not ch:
            raise BizError("推送渠道不存在", code=3081, status_code=404)
        return ch

    @staticmethod
    def to_dict(ch: NotifyChannel) -> dict:
        try:
            masked = mask_secret(decrypt_secret(ch.target_encrypted))
        except Exception:  # noqa: BLE001
            masked = "****"
        return {
            "id": str(ch.id),
            "channel_type": ch.channel_type,
            "name": ch.name,
            "target_mask": masked,
            "secret_configured": bool(ch.secret_encrypted),
            "enabled": ch.enabled,
            "created_at": ch.created_at.isoformat() if ch.created_at else None,
        }
