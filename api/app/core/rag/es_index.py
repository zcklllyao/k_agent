"""Elasticsearch 索引定义与初始化。

统一索引 comet_chunks（个人版数据量小，单索引 + user_id 过滤足够）。
关键词检索按语言使用 IK 中文分词或 Elasticsearch 内置 English analyzer。
向量维度由 EMBEDDING_DIMS 配置（当前为 1024）。
"""
from app.config import settings
from app.core.logging import get_logger
from app.db.elastic import get_es

logger = get_logger(__name__)

CHUNKS_INDEX = "comet_chunks"
VECTOR_DIMS = settings.embedding_dims
INDEX_MAPPING_VERSION = 2

# 父子分块：child 用于向量召回，parent 提供更大上下文
CHUNK_TYPE_CHILD = "child"
CHUNK_TYPE_PARENT = "parent"
CHUNK_TYPE_IMAGE = "image_desc"

_MAPPING = {
    "mappings": {
        "properties": {
            "user_id": {"type": "keyword"},
            "kb_id": {"type": "keyword"},  # 所属知识库（多知识库检索范围过滤）
            "source_type": {"type": "keyword"},  # document | image
            "source_id": {"type": "keyword"},  # documents.id / images.id
            "doc_name": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "chunk_type": {"type": "keyword"},  # child | parent | image_desc
            "parent_id": {"type": "keyword"},  # child 指向其 parent chunk_id
            # 同一份原文写入两个子字段：中文用 IK，英文用内置 english analyzer。
            "content": {
                "type": "text",
                "index": False,
                "fields": {
                    "zh": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    },
                    "en": {
                        "type": "text",
                        "analyzer": "english",
                    },
                },
            },
            "language": {"type": "keyword"},  # zh | en | mixed
            "tags": {"type": "keyword"},
            "vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "created_at": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


async def ensure_index() -> None:
    """确保 comet_chunks 使用当前中英文多字段 mapping。

    - 不存在：按正确 mapping 创建。
    mapping 版本不匹配时自动通过临时索引重建，并从 content 回填 language。
    """
    es = get_es()
    exists = await es.indices.exists(index=CHUNKS_INDEX)
    if not exists:
        await es.indices.create(index=CHUNKS_INDEX, body=_MAPPING)
        logger.info("创建 ES 索引: %s", CHUNKS_INDEX)
        return

    if await _mapping_is_current(es):
        return
    logger.warning(
        "ES 索引 %s mapping 版本过旧，开始自动重建中英文分词索引…",
        CHUNKS_INDEX,
    )
    try:
        await _rebuild_index(es)
        logger.info("ES 中英文分词索引重建完成: %s", CHUNKS_INDEX)
    except Exception as e:
        logger.error("ES 中英文分词索引重建失败: %s", e, exc_info=True)
        raise


async def _mapping_is_current(es) -> bool:
    """确认 language 字段和 content.zh/content.en 子字段均已存在。"""
    try:
        resp = await es.indices.get_mapping(index=CHUNKS_INDEX)
        props = resp[CHUNKS_INDEX]["mappings"].get("properties", {})
        content_fields = props.get("content", {}).get("fields", {})
        return (
            props.get("kb_id", {}).get("type") == "keyword"
            and props.get("language", {}).get("type") == "keyword"
            and content_fields.get("zh", {}).get("analyzer") == "ik_max_word"
            and content_fields.get("en", {}).get("analyzer") == "english"
        )
    except Exception as e:
        logger.warning("读取 ES mapping 失败: %s", e)
        return False


async def _rebuild_index(es) -> None:
    """通过临时索引把 comet_chunks 按当前 mapping 重建。保留全部存量文档。"""
    from elasticsearch import helpers

    from app.core.rag.language import detect_text_language

    tmp_index = f"{CHUNKS_INDEX}_reindex_tmp"
    # 清理可能残留的临时索引
    if await es.indices.exists(index=tmp_index):
        await es.indices.delete(index=tmp_index)
    # 1) 建临时索引（正确 mapping）
    await es.indices.create(index=tmp_index, body=_MAPPING)
    # 2) 原 → 临时（refresh 确保数据落盘后再删原索引）
    await es.reindex(
        body={"source": {"index": CHUNKS_INDEX}, "dest": {"index": tmp_index}},
        refresh=True,
        wait_for_completion=True,
    )
    # reindex 只复制 _source；为存量数据补上语言标记。
    language_updates = []
    async for hit in helpers.async_scan(
        es,
        index=tmp_index,
        query={"query": {"match_all": {}}, "_source": ["content"]},
    ):
        language_updates.append(
            {
                "_op_type": "update",
                "_index": tmp_index,
                "_id": hit["_id"],
                "doc": {
                    "language": detect_text_language(
                        hit.get("_source", {}).get("content", "")
                    )
                },
            }
        )
    if language_updates:
        await helpers.async_bulk(es, language_updates, refresh=True)
    # 3) 删原索引，按正确 mapping 重建
    await es.indices.delete(index=CHUNKS_INDEX)
    await es.indices.create(index=CHUNKS_INDEX, body=_MAPPING)
    # 4) 临时 → 原
    await es.reindex(
        body={"source": {"index": tmp_index}, "dest": {"index": CHUNKS_INDEX}},
        refresh=True,
        wait_for_completion=True,
    )
    # 5) 删临时索引
    await es.indices.delete(index=tmp_index)


__all__ = [
    "CHUNKS_INDEX",
    "VECTOR_DIMS",
    "INDEX_MAPPING_VERSION",
    "CHUNK_TYPE_CHILD",
    "CHUNK_TYPE_PARENT",
    "CHUNK_TYPE_IMAGE",
    "ensure_index",
]
