"""知识库文档业务服务：上传/网页导入/列表/状态/重试/删除/检索。"""
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.core.rag.es_store import delete_by_source
from app.core.rag.parser import SUPPORTED_EXTS
from app.core.rag.search import hybrid_search
from app.core.storage import build_file_key, get_storage
from app.models.document_model import (
    DOC_STATUS_PENDING,
    Document,
)
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.repositories.tag_repository import TagRepository

logger = get_logger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class DocumentService:
    PREVIEW_MAX_CHARS = 80000  # 文档预览最大返回字符数（超出截断）

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DocumentRepository(session)
        self.tag_repo = TagRepository(session)
        self.kb_repo = KnowledgeBaseRepository(session)

    async def _dispatch_parse(self, document_id: uuid.UUID) -> None:
        # 延迟导入，避免 worker 未装时影响导入
        from app.tasks.parse import parse_document_task

        parse_document_task.delay(str(document_id))

    async def _dispatch_overview(self, user_id: uuid.UUID, kb_id: uuid.UUID | None) -> None:
        if not kb_id:
            return
        from app.tasks.knowledge_base_overview import generate_knowledge_base_overview_task

        generate_knowledge_base_overview_task.delay(str(user_id), str(kb_id))

    async def _resolve_kb_id(
        self, user_id: uuid.UUID, kb_id: uuid.UUID | None
    ) -> uuid.UUID:
        """确定文档归属库：指定了就校验归属，没指定落默认库。"""
        if kb_id:
            kb = await self.kb_repo.get(user_id, kb_id)
            if not kb:
                raise BizError("知识库不存在", code=3040, status_code=404)
            return kb.id
        return (await self.kb_repo.ensure_default(user_id)).id

    async def upload(
        self,
        user_id: uuid.UUID,
        file_name: str,
        content: bytes,
        kb_id: uuid.UUID | None = None,
    ) -> Document:
        ext = Path(file_name).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            raise BizError(f"不支持的文件类型: {ext}", code=3001)
        if len(content) > MAX_FILE_SIZE:
            raise BizError("文件超过 50MB 限制", code=3005)

        resolved_kb = await self._resolve_kb_id(user_id, kb_id)
        doc_id = uuid.uuid4()
        file_key = build_file_key(str(user_id), "documents", str(doc_id), ext)
        await get_storage().save(file_key, content)

        doc = Document(
            id=doc_id,
            user_id=user_id,
            kb_id=resolved_kb,
            file_name=file_name,
            file_ext=ext,
            file_size=len(content),
            file_key=file_key,
            source_type="file",
            status=DOC_STATUS_PENDING,
        )
        await self.repo.create(doc)
        await self._dispatch_parse(doc_id)
        logger.info("文档上传: user=%s id=%s name=%s", user_id, doc_id, file_name)
        return doc

    async def import_url(
        self, user_id: uuid.UUID, url: str, kb_id: uuid.UUID | None = None
    ) -> Document:
        from app.core.rag.web_crawler import fetch_url_content

        resolved_kb = await self._resolve_kb_id(user_id, kb_id)
        title, text = await fetch_url_content(url)
        doc_id = uuid.uuid4()
        file_key = build_file_key(str(user_id), "documents", str(doc_id), ".txt")
        await get_storage().save(file_key, text.encode("utf-8"))

        doc = Document(
            id=doc_id,
            user_id=user_id,
            kb_id=resolved_kb,
            file_name=f"{title}.txt",
            file_ext=".txt",
            file_size=len(text.encode("utf-8")),
            file_key=file_key,
            source_type="url",
            source_url=url,
            status=DOC_STATUS_PENDING,
        )
        await self.repo.create(doc)
        await self._dispatch_parse(doc_id)
        logger.info("网页导入: user=%s id=%s url=%s", user_id, doc_id, url)
        return doc

    async def _get_or_404(
        self, user_id: uuid.UUID, doc_id: uuid.UUID
    ) -> Document:
        doc = await self.repo.get(user_id, doc_id)
        if not doc:
            raise BizError("文档不存在", code=3006, status_code=404)
        return doc

    async def list_documents(
        self,
        user_id: uuid.UUID,
        page: int,
        page_size: int,
        tag: str | None = None,
        kb_id: uuid.UUID | None = None,
    ) -> tuple[list[Document], int]:
        return await self.repo.list_paged(user_id, page, page_size, tag, kb_id)

    async def get_detail(self, user_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
        return await self._get_or_404(user_id, doc_id)

    async def retry(self, user_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
        doc = await self._get_or_404(user_id, doc_id)
        doc.status = DOC_STATUS_PENDING
        doc.progress = 0.0
        doc.error_msg = None
        await self.repo.save(doc)
        await self._dispatch_parse(doc_id)
        return doc

    async def delete(self, user_id: uuid.UUID, doc_id: uuid.UUID) -> None:
        doc = await self._get_or_404(user_id, doc_id)
        kb_id = doc.kb_id
        # 清 ES chunk + 存储文件 + PG 记录
        await delete_by_source(str(user_id), str(doc_id))
        try:
            await get_storage().delete(doc.file_key)
        except Exception as e:
            logger.warning("删除存储文件失败（忽略）: %s", e)
        await self.repo.delete(doc)
        await self._dispatch_overview(user_id, kb_id)
        logger.info("删除文档: user=%s id=%s", user_id, doc_id)

    async def delete_many(
        self, user_id: uuid.UUID, doc_ids: list[uuid.UUID]
    ) -> dict[str, int]:
        """批量删除文档及其 ES 分片和本地/OSS 原文件。"""
        # 去重后再查库，避免重复请求导致计数与删除次数不一致。
        unique_ids = list(dict.fromkeys(doc_ids))
        docs = await self.repo.list_by_ids(user_id, unique_ids)
        kb_ids = {doc.kb_id for doc in docs if doc.kb_id}
        found_ids = {doc.id for doc in docs}

        for doc in docs:
            await delete_by_source(str(user_id), str(doc.id))
            try:
                await get_storage().delete(doc.file_key)
            except Exception as e:
                # 原文件已不存在时不阻断数据库和索引清理。
                logger.warning("批量删除存储文件失败（忽略）: id=%s err=%s", doc.id, e)
            await self.session.delete(doc)

        if docs:
            await self.session.commit()
            for kb_id in kb_ids:
                await self._dispatch_overview(user_id, kb_id)
        logger.info(
            "批量删除文档: user=%s requested=%d deleted=%d skipped=%d",
            user_id,
            len(unique_ids),
            len(docs),
            len(unique_ids) - len(found_ids),
        )
        return {
            "requested": len(unique_ids),
            "deleted": len(docs),
            "skipped": len(unique_ids) - len(found_ids),
        }

    async def search(
        self,
        user_id: uuid.UUID,
        query: str,
        top_k: int,
        tags: list[str] | None,
    ) -> list[dict]:
        return await hybrid_search(
            self.session,
            user_id,
            query,
            top_k=top_k,
            tags=tags,
            source_type="document",
        )

    async def move_to_kb(
        self, user_id: uuid.UUID, doc_id: uuid.UUID, kb_id: uuid.UUID
    ) -> Document:
        """把文档移动到另一个知识库，并同步回写 ES chunk 的 kb_id。"""
        from app.core.rag.es_store import update_kb_by_source

        doc = await self._get_or_404(user_id, doc_id)
        old_kb_id = doc.kb_id
        kb = await self.kb_repo.get(user_id, kb_id)
        if not kb:
            raise BizError("知识库不存在", code=3040, status_code=404)
        doc.kb_id = kb.id
        await self.repo.save(doc)
        try:
            await update_kb_by_source(str(user_id), str(doc_id), str(kb.id))
        except Exception as e:
            logger.warning("移动文档回写 ES kb_id 失败（忽略）: %s", e)
        await self._dispatch_overview(user_id, doc.kb_id)
        if old_kb_id and old_kb_id != doc.kb_id:
            await self._dispatch_overview(user_id, old_kb_id)
        return doc

    async def preview(self, user_id: uuid.UUID, doc_id: uuid.UUID) -> dict:
        """读取文档原文内容供查看：md/txt 保留原文，pdf/docx/html 提取纯文本。

        从对象存储取原始文件按类型解析，超长截断（带 truncated 标记）。
        """
        from app.core.rag.parser import decode_text, parse_document

        doc = await self._get_or_404(user_id, doc_id)
        try:
            raw = await get_storage().get(doc.file_key)
        except Exception as e:
            logger.warning("读取文档原文失败: id=%s err=%s", doc_id, e)
            raise BizError("原始文件读取失败，可能已被清理", code=3033) from e

        ext = (doc.file_ext or "").lower()
        is_markdown = ext in (".md", ".markdown")
        try:
            if is_markdown or ext == ".txt":
                # 保留原始文本（markdown 交前端渲染，纯文本原样展示）
                text = decode_text(raw)
            else:
                text = parse_document(ext, raw)
        except Exception as e:
            logger.warning("文档预览解析失败: id=%s err=%s", doc_id, e)
            raise BizError(f"内容解析失败：{e}", code=3034) from e

        text = (text or "").strip()
        truncated = len(text) > self.PREVIEW_MAX_CHARS
        if truncated:
            text = text[: self.PREVIEW_MAX_CHARS]
        return {
            "id": str(doc.id),
            "file_name": doc.file_name,
            "file_ext": ext,
            "is_markdown": is_markdown,
            "source_url": doc.source_url,
            "content": text,
            "truncated": truncated,
        }

    async def to_out_dict(self, doc: Document) -> dict:
        tags = await self.tag_repo.get_document_tags(doc.id)
        return {
            "id": str(doc.id),
            "kb_id": str(doc.kb_id) if doc.kb_id else None,
            "file_name": doc.file_name,
            "file_ext": doc.file_ext,
            "file_size": doc.file_size,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
            "status": doc.status,
            "progress": doc.progress,
            "chunk_num": doc.chunk_num,
            "error_msg": doc.error_msg,
            "tags": tags,
            "created_at": doc.created_at.isoformat(),
        }
