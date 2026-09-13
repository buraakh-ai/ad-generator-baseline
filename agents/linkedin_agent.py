"""LinkedIn agent — writes a dedicated business-tone LinkedIn post (the
original app reused the Facebook caption for LinkedIn; this agent gets its
own prompt) and, once an image exists, can post it via
tools/linkedin_tool.py, either to a personal profile or a company page."""
from agents._common import generate_platform_copy
from tools.linkedin_tool import post_to_linkedin as _post_to_linkedin
from tools.linkedin_tool import post_to_linkedin_company as _post_to_linkedin_company


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_linkedin", complexity="high", **brief)


def post(image_local_path: str, caption: str) -> str:
    return _post_to_linkedin(image_local_path, caption)


def post_as_company(image_local_path: str, caption: str, organization_id: str) -> str:
    return _post_to_linkedin_company(image_local_path, caption, organization_id)
