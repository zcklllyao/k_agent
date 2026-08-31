"""知识库数据访问层。所有查询强制带 user_id 隔离。"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_model import Document
from app.models.image_model import Image
from app.models.knowledge_base_model import KnowledgeBase


class KnowledgeBaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, kb: KnowledgeBase) -> KnowledgeBase:
        self.session.add(kb)
        await self.session.commit()
        await self.session.refresh(kb)
        return kb

    async def get(self, user_id: uuid.UUID, kb_id: uuid.UUID) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> list[KnowledgeBase]:
        """默认库优先、其余按创建时间正序。"""
        stmt = (
            select(KnowledgeBase)
            .where(KnowledgeBase.user_id == user_id)
            .order_by(
                KnowledgeBase.is_default.desc(), KnowledgeBase.created_at.asc()
            )
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_default(self, user_id: uuid.UUID) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.is_default.is_(True),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def ensure_default(self, user_id: uuid.UUID) -> KnowledgeBase:
        """取用户默认知识库；不存在则创建。"""
        kb = await self.get_default(user_id)
        if kb:
            return kb
        kb = KnowledgeBase(
            user_id=user_id,
            name="默认知识库",
            description="未分类资料默认归入此库",
            icon="📚",
            color="#155EEF",
            is_default=True,
            chat_enabled=True,
        )
        return await self.create(kb)

    async def get_by_name(
        self, user_id: uuid.UUID, name: str
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id, KnowledgeBase.name == name
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def ensure_named(
        self,
        user_id: uuid.UUID,
        name: str,
        *,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        chat_enabled: bool = False,
    ) -> KnowledgeBase:
        """按名称取知识库，不存在则创建（用于「深度研究报告」等专用库）。"""
        kb = await self.get_by_name(user_id, name)
        if kb:
            return kb
        kb = KnowledgeBase(
            user_id=user_id,
            name=name,
            description=description,
            icon=icon,
            color=color,
            is_default=False,
            chat_enabled=chat_enabled,
        )
        return await self.create(kb)

    async def list_chat_enabled_ids(self, user_id: uuid.UUID) -> list[str]:
        """对话检索范围：所有 chat_enabled=True 的知识库 id（字符串）。"""
        stmt = select(KnowledgeBase.id).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.chat_enabled.is_(True),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return [str(r) for r in rows]

    async def counts(self, user_id: uuid.UUID) -> dict[uuid.UUID, dict[str, int]]:
        """统计每个知识库的文档数 / 图片数（实时，不冗余存储）。"""
        result: dict[uuid.UUID, dict[str, int]] = {}
        doc_rows = await self.session.execute(
            select(Document.kb_id, func.count())
            .where(Document.user_id == user_id, Document.kb_id.isnot(None))
            .group_by(Document.kb_id)
        )
        for kb_id, cnt in doc_rows.all():
            result.setdefault(kb_id, {"doc_count": 0, "image_count": 0})
            result[kb_id]["doc_count"] = int(cnt)
        img_rows = await self.session.execute(
            select(Image.kb_id, func.count())
            .where(Image.user_id == user_id, Image.kb_id.isnot(None))
            .group_by(Image.kb_id)
        )
        for kb_id, cnt in img_rows.all():
            result.setdefault(kb_id, {"doc_count": 0, "image_count": 0})
            result[kb_id]["image_count"] = int(cnt)
        return result

    async def save(self, kb: KnowledgeBase) -> KnowledgeBase:
        await self.session.commit()
        await self.session.refresh(kb)
        return kb

    async def delete(self, kb: KnowledgeBase) -> None:
        await self.session.delete(kb)
        await self.session.commit()
