"""
Upload raw email content to S3 / MinIO.
Key pattern: raw-emails/{user_id}/{year}/{month}/{message_id}.json
"""
import json
import os
import structlog
from datetime import datetime, timezone

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from services.ingestion.gmail_client import ParsedEmail

log = structlog.get_logger()

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "lifeadmin-emails")
S3_PREFIX = os.environ.get("S3_PREFIX", "raw-emails")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT_URL", "")  # Empty = AWS; set for MinIO
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", os.environ.get("MINIO_ROOT_USER", "minioadmin"))
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin123"))

_s3_client: BaseClient | None = None


def _get_s3() -> BaseClient:
    global _s3_client
    if _s3_client is None:
        kwargs = {
            "region_name": AWS_REGION,
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        }
        if S3_ENDPOINT:
            kwargs["endpoint_url"] = S3_ENDPOINT
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def _build_s3_key(user_id: str, message_id: str) -> str:
    now = datetime.now(timezone.utc)
    return f"{S3_PREFIX}/{user_id}/{now.year}/{now.month:02d}/{message_id}.json"


async def upload_email(user_id: str, email: ParsedEmail) -> str:
    """
    Upload email to S3.

    Args:
        user_id: The user's UUID
        email: ParsedEmail object

    Returns:
        S3 key of the uploaded object
    """
    s3 = _get_s3()
    key = _build_s3_key(user_id, email.message_id)

    payload = {
        "message_id": email.message_id,
        "thread_id": email.thread_id,
        "subject": email.subject,
        "sender": email.sender,
        "received_at": email.received_at,
        "body_text": email.body_text,
        "snippet": email.snippet,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }

    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False),
            ContentType="application/json",
            Metadata={
                "user-id": user_id,
                "message-id": email.message_id,
            },
        )
        log.info("Email uploaded to S3", s3_key=key, user_id=user_id)
        return key

    except ClientError as e:
        log.error("S3 upload failed", error=str(e), s3_key=key)
        raise


def ensure_bucket_exists() -> None:
    """Create the S3 bucket if it doesn't exist (for local MinIO dev)."""
    s3 = _get_s3()
    try:
        s3.head_bucket(Bucket=S3_BUCKET)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            s3.create_bucket(Bucket=S3_BUCKET)
            log.info("S3 bucket created", bucket=S3_BUCKET)
        else:
            raise
