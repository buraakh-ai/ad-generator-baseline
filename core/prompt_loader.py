"""Loads LLM prompt templates from prompts/*.yaml so every prompt in the
project can be edited without touching Python. Each yaml file has an
optional `system` key and a `user` key, both plain strings with
{placeholder} slots filled in by render()."""
import os

import yaml

_PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts")

_cache = {}


class _DefaultDict(dict):
    def __missing__(self, key):
        return ""


def load_prompt(name: str) -> dict:
    if name in _cache:
        return _cache[name]
    path = os.path.join(_PROMPTS_DIR, f"{name}.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _cache[name] = data
    return data


def render(name: str, **kwargs):
    """Returns (system_prompt, user_prompt) with {placeholders} filled in
    from kwargs. Missing keys render as empty string rather than raising."""
    data = load_prompt(name)
    safe_kwargs = _DefaultDict({k: ("" if v is None else v) for k, v in kwargs.items()})
    system_tpl = data.get("system", "") or ""
    user_tpl = data.get("user", "") or ""
    return system_tpl.format_map(safe_kwargs), user_tpl.format_map(safe_kwargs)
