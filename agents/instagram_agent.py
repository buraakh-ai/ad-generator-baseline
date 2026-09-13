"""Instagram agent — writes Instagram-specific ad copy and, once an image
exists, can post it to the connected Instagram account via
tools/instagram_tool.py."""
from agents._common import generate_platform_copy
from tools.instagram_tool import post_to_instagram as _post_to_instagram


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_instagram", complexity="high", **brief)


def post(image_local_path: str, caption: str) -> str:
    return _post_to_instagram(image_local_path, caption)
