"""启动时自动把数据库升级到最新迁移（alembic upgrade head）。

以编程方式调用 Alembic，路径相对本文件定位（不依赖运行时 cwd）。
migrations/env.py 内部用 asyncio.run 跑异步迁移，故本函数必须在「非事件循环」
线程中执行；在 FastAPI lifespan 里通过 asyncio.to_thread 调用 upgrade_to_head_sync。
"""
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.logging import get_logger

logger = get_logger(__name__)

# 本文件 app/db/migrate.py → parents[2] = api 根目录（migrations 所在）
_API_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _API_ROOT / "migrations"


def _build_config() -> Config:
    # 不传 alembic.ini 路径：使 env.py 的 fileConfig 分支跳过，避免覆盖应用已初始化的日志配置
    # （env.py 通过 app.config.settings 读取数据库 URL，不依赖 ini）。
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    return cfg


def upgrade_to_head_sync() -> None:
    """同步执行 alembic upgrade head。必须在非事件循环线程中调用。"""
    cfg = _build_config()
    command.upgrade(cfg, "head")


async def upgrade_to_head() -> None:
    """在 lifespan 中安全调用：放到工作线程跑，避免与当前事件循环冲突。"""
    try:
        await asyncio.to_thread(upgrade_to_head_sync)
        logger.info("数据库迁移已升级到最新（alembic upgrade head）")
    except Exception as e:
        logger.error("数据库自动迁移失败: %s", e, exc_info=True)
        raise


__all__ = ["upgrade_to_head", "upgrade_to_head_sync"]
