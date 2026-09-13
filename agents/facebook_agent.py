"""Facebook agent — writes Facebook-specific ad copy and, once an image
exists, can post it to the connected Facebook Page via
tools/facebook_tool.py."""
from agents._common import generate_platform_copy
from tools.facebook_tool import post_to_facebook as _post_to_facebook


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_facebook", complexity="high", **brief)


def post(image_local_path: str, caption: str) -> str:
    return _post_to_facebook(image_local_path, caption)
