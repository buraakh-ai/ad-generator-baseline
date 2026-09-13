"""AWS Secrets Manager helpers shared by the Facebook/Instagram/LinkedIn
tools. Falls back gracefully (returns None) if AWS credentials aren't
configured or the secret doesn't exist yet, so local dev without AWS still
works off the .env-provided fallback tokens."""
import boto3

from core.config import settings


def aws_client(service):
    """Builds a boto3 client for `service`. Only passes explicit static
    credentials when both are configured — otherwise boto3 falls through to
    its default credential chain (env vars, ~/.aws/credentials, or an ECS/App
    Runner/EC2 instance role), instead of erroring on an empty access key."""
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client(service, **kwargs)


def get_secret(secret_name: str):
    client = aws_client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return response["SecretString"]
    except client.exceptions.ResourceNotFoundException:
        print(f"[secrets] no secret at {secret_name} yet")
        return None
    except Exception as e:
        print(f"[secrets] could not reach AWS Secrets Manager for {secret_name}: {e}")
        return None


def put_secret(secret_name: str, secret_value: str):
    client = aws_client("secretsmanager")
    try:
        client.put_secret_value(SecretId=secret_name, SecretString=secret_value)
    except client.exceptions.ResourceNotFoundException:
        client.create_secret(Name=secret_name, SecretString=secret_value)
