"""Verifier 模块的 prompt 渲染器(独立加载 ./prompts/)。"""
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_verifier_prompt(template_name: str, **context) -> str:
    """渲染 verifier prompt 模板。"""
    return _get_env().get_template(template_name).render(**context)


__all__ = ["render_verifier_prompt"]
