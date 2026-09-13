"""Uploads a locally generated ad image to S3 so social platforms (which
require a public URL, not a file upload) can fetch it."""
from datetime import datetime

from core.config import settings
from tools.secrets_tool import aws_client


def upload_to_s3(local_path: str, prefix: str = "ad") -> str:
    s3 = aws_client("s3")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.jpg"
    print(f"[s3] uploading {local_path} to s3://{settings.aws_bucket_name}/{filename}...")
    s3.upload_file(
        local_path,
        settings.aws_bucket_name,
        filename,
        ExtraArgs={"ContentType": "image/jpeg", "ACL": "public-read"},
    )
    public_url = f"https://{settings.aws_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{filename}"
    print(f"[s3] uploaded: {public_url}")
    return public_url
