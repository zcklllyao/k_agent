"""Agent prompt 模板渲染器：加载 agent/prompts/ 下的 jinja2 模板。"""
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_agent_prompt(template_name: str, **context) -> str:
    return _get_env().get_template(template_name).render(**context)


__all__ = ["render_agent_prompt"]
