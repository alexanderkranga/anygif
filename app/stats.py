"""S3-backed GIF generation counter with optimistic concurrency control."""

from __future__ import annotations

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_STATS_KEY = "stats.json"
_MAX_RETRIES = 5

_s3 = None


def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def _bucket() -> str:
    return os.environ["S3_STATS_BUCKET"]


def get_gif_count() -> int:
    """Read current GIF count from S3. Returns 0 if not yet initialised."""
    try:
        resp = _get_s3().get_object(Bucket=_bucket(), Key=_STATS_KEY)
        data = json.loads(resp["Body"].read())
        return int(data.get("count", 0))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return 0
        raise


def increment_gif_count() -> int:
    """
    Atomically increment the GIF counter using ETag-based optimistic locking.
    Retries up to _MAX_RETRIES times on concurrent write conflicts (HTTP 412).
    Returns the new count.
    """
    s3 = _get_s3()
    bucket = _bucket()

    for attempt in range(_MAX_RETRIES):
        # Read current value + ETag
        try:
            resp = s3.get_object(Bucket=bucket, Key=_STATS_KEY)
            etag = resp["ETag"]
            current = int(json.loads(resp["Body"].read()).get("count", 0))
            condition = {"IfMatch": etag}
        except ClientError as e:
            if e.response["Error"]["Code"] != "NoSuchKey":
                raise
            current = 0
            condition = {"IfNoneMatch": "*"}

        new_count = current + 1
        body = json.dumps({"count": new_count}).encode()

        try:
            s3.put_object(
                Bucket=bucket,
                Key=_STATS_KEY,
                Body=body,
                ContentType="application/json",
                **condition,
            )
            return new_count
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("PreconditionFailed", "ConditionalRequestConflict"):
                logger.debug("Stats increment conflict on attempt %d, retrying", attempt + 1)
                continue
            raise

    logger.error("Stats increment failed after %d retries", _MAX_RETRIES)
    raise RuntimeError("Could not increment gif count after retries")
