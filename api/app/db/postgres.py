"""PostgreSQL 异步连接（SQLAlchemy 2.0）。

连接池参数显式化：pool_pre_ping 剔除失效连接，
pool_recycle 防被 DB 端断开，statement_timeout 防慢查询挂死。
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    future=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=settings.db_pool_pre_ping,
    # asyncpg 用 server_settings 设单条 SQL 超时（毫秒）
    connect_args={
        "server_settings": {
            "timezone": "UTC",
            "statement_timeout": str(settings.db_statement_timeout_ms),
        }
    },
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def ping() -> bool:
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_pool_status() -> dict:
    """连接池状态（监控用）。"""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
    }


def create_task_engine():
    """为 Celery 任务创建独立引擎（绑定当前事件循环，用完即弃）。

    Celery 每个任务用新的 asyncio 事件循环，全局单例引擎的连接池会绑定到
    已关闭的旧循环导致报错，故任务内用独立引擎 + NullPool（不缓存连接）。
    """
    from sqlalchemy.pool import NullPool

    return create_async_engine(
        settings.database_url,
        echo=settings.db_echo,
        future=True,
        poolclass=NullPool,
        connect_args={
            "server_settings": {
                "timezone": "UTC",
                "statement_timeout": str(settings.db_statement_timeout_ms),
            }
        },
    )


async def close() -> None:
    await engine.dispose()
