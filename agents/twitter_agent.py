"""X/Twitter copy agent. No posting API for X in this project — copy only,
for the user to paste manually."""
from agents._common import generate_platform_copy


def write_copy(**brief) -> str:
    return generate_platform_copy("ad_copy_twitter", complexity="high", **brief)
