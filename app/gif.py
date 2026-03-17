"""Async wrapper around anygif.sh for GIF generation."""

import asyncio
import os
import uuid
import logging

from app import config

logger = logging.getLogger(__name__)


class GifGenerationError(Exception):
    pass


def _add_seconds_to_timestamp(timestamp: str, seconds: int) -> str:
    """Add seconds to an mm:ss or m:ss timestamp, returning mm:ss."""
    parts = timestamp.split(":")
    mins = int(parts[0])
    secs = int(parts[1])
    total = mins * 60 + secs + seconds
    return f"{total // 60}:{total % 60:02d}"


async def _run_anygif(
    video_url: str,
    start_time: str,
    end_time: str,
    output_path: str,
    proxy: str | None = None,
) -> tuple[int, bytes, bytes]:
    """Run anygif subprocess, return (returncode, stdout, stderr)."""
    cmd = ["anygif", "--fps", "24"]
    if proxy:
        cmd += ["--proxy", proxy]
    cmd += [video_url, start_time, end_time, output_path]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise GifGenerationError("GIF generation timed out (120s)")

    return proc.returncode, stdout, stderr


async def generate_gif(video_url: str, start_time: str, duration: int) -> bytes:
    """Run anygif to generate a GIF and return the bytes.

    Tries without proxy first. If that fails and a proxy is configured,
    retries through the Decodo residential proxy.
    """
    end_time = _add_seconds_to_timestamp(start_time, duration)
    output_path = f"/tmp/{uuid.uuid4()}.mp4"

    try:
        # First attempt: no proxy
        first_error = None
        returncode = 1
        try:
            returncode, stdout, stderr = await _run_anygif(
                video_url, start_time, end_time, output_path
            )
        except GifGenerationError as e:
            first_error = e

        # If failed, try with proxy
        if returncode != 0 or first_error:
            proxy_url = config.get_proxy_url()
            if proxy_url:
                logger.info("Direct download failed, retrying with proxy")
                # This may raise GifGenerationError (e.g. timeout) — let it propagate
                returncode, stdout, stderr = await _run_anygif(
                    video_url, start_time, end_time, output_path, proxy=proxy_url
                )
                first_error = None
            elif first_error:
                raise first_error

        if first_error:
            raise first_error

        if returncode != 0:
            logger.error("anygif failed (rc=%d)", returncode)
            raise GifGenerationError("GIF generation failed")

        with open(output_path, "rb") as f:
            data = f.read()

        if not data:
            raise GifGenerationError("GIF generation produced empty output")

        return data

    finally:
        try:
            os.unlink(output_path)
        except FileNotFoundError:
            pass
