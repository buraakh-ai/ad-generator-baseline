"""Pydantic request/response models for the FastAPI backend. Field names
match the original Flask app's JSON contracts so the frontend/MCP layers
don't need to know anything changed under the hood."""
from typing import Optional

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    company_name: str = ""
    product_description: str = ""
    ad_idea: str = ""
    event_context: Optional[str] = None
    company_url: Optional[str] = None


class RetryEventRequest(BaseModel):
    company_name: str = ""
    company_url: str = ""


class GenerateImageRequest(BaseModel):
    company_name: str = ""
    instagram_copy: str = ""
    image_headline: str = ""
    event_context: str = ""
    company_details: dict = {}
    logo_url: Optional[str] = None
    custom_prompt: str = ""


class SwitchProviderRequest(BaseModel):
    provider: str


class PostRequest(BaseModel):
    caption: str = ""
    image_url: str = ""
