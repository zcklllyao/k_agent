"""记忆萃取 prompt 模板渲染器：统一加载 prompts/ 下的 jinja2 模板。

模板与代码分离，便于调整 prompt 而不动逻辑。环境单例缓存，避免重复初始化。
"""
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),  # 非 HTML，不转义
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(template_name: str, **context) -> str:
    """渲染指定模板。template_name 形如 'extract_statement.jinja2'。"""
    template = _get_env().get_template(template_name)
    return template.render(**context)


__all__ = ["render_prompt"]
