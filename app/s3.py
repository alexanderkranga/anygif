"""S3 upload helper using boto3."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import boto3

from app.config import get_s3_bucket

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3")
    return _client


def set_client(client) -> None:
    global _client
    _client = client


async def upload_gif(data: bytes, key: str) -> str:
    """Upload GIF bytes to S3 and return the key."""
    bucket = get_s3_bucket()

    def _upload():
        get_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType="video/mp4",
        )

    await asyncio.to_thread(_upload)
    logger.info("Uploaded %s to s3://%s/%s (%d bytes)", key, bucket, key, len(data))
    return key
