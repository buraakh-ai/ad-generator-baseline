"""Image-provider chain configuration. Provider list/order/enabled state
and prompt prefix/suffix/override live in image_config.json (unchanged
shape from the original project, still hand-editable) so switching models
or reordering the fallback chain never requires a code change."""
import json
import os

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "image_config.json")

_DEFAULT_CONFIG = {
    "active_provider": "openai_image",
    "providers": [
        {"name": "openai_image", "label": "OpenAI gpt-image-2.5-sunburst (best quality)", "enabled": True, "api_key": ""},
        {"name": "openai_image_fallback", "label": "OpenAI gpt-image-1 (fallback)", "enabled": True, "api_key": ""},
        {"name": "openai_dalle3", "label": "OpenAI DALL-E 3 (last resort)", "enabled": True, "api_key": ""},
    ],
    "prompt_prefix": "", "prompt_suffix": "", "override_prompt": "",
}


def load_config():
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        print(f"[image_config] active_provider: {cfg.get('active_provider', 'openai_image')}")
        return cfg
    except Exception as e:
        print(f"[image_config] {e} — using defaults")
        return dict(_DEFAULT_CONFIG)


def save_active_provider(provider_name):
    try:
        with open(_CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        cfg["active_provider"] = provider_name
        with open(_CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"[image_config] switched active provider to: {provider_name}")
    except Exception as e:
        print(f"[image_config] failed to save provider: {e}")


def get_providers(config):
    return [p for p in config.get("providers", []) if p.get("enabled", True)]


def get_active_provider(config):
    active = config.get("active_provider", "openai_image")
    providers = get_providers(config)
    for p in providers:
        if p["name"] == active:
            return p
    return providers[0] if providers else _DEFAULT_CONFIG["providers"][0]


def get_next_provider(config):
    active = config.get("active_provider", "openai_image")
    providers = get_providers(config)
    names = [p["name"] for p in providers]
    if active in names:
        idx = names.index(active)
        if idx + 1 < len(names):
            return providers[idx + 1]
    return None
