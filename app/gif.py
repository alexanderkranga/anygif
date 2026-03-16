"""Async wrapper around anygif.sh for GIF generation."""

import asyncio
import os
import re
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


def _sanitize_output(raw: bytes, max_len: int = 2000) -> str:
    """Decode subprocess output, strip URLs, truncate."""
    text = raw.decode("utf-8", errors="replace").strip()
    # Remove anything that looks like a URL to avoid leaking video/proxy URLs
    text = re.sub(r"https?://\S+", "<URL>", text)
    if len(text) > max_len:
        return text[:max_len] + "... (truncated)"
    return text


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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
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
    has_proxy = config.get_proxy_url() is not None

    logger.info(
        "Starting generation: start=%s end=%s duration=%ds proxy_available=%s",
        start_time, end_time, duration, has_proxy,
    )

    try:
        # First attempt: no proxy
        first_error = None
        returncode = 1
        stdout = stderr = b""
        try:
            logger.info("Attempt 1/2: direct (no proxy)")
            returncode, stdout, stderr = await _run_anygif(
                video_url, start_time, end_time, output_path
            )
            logger.info("Attempt 1/2: exited with rc=%d", returncode)
            if stdout:
                logger.info("Attempt 1/2 stdout: %s", _sanitize_output(stdout))
            if returncode != 0 and stderr:
                logger.warning("Attempt 1/2 stderr: %s", _sanitize_output(stderr))
        except GifGenerationError as e:
            logger.warning("Attempt 1/2 failed: %s", e)
            first_error = e

        # If failed, try with proxy
        if returncode != 0 or first_error:
            proxy_url = config.get_proxy_url()
            if proxy_url:
                logger.info("Attempt 2/2: retrying with proxy")
                # This may raise GifGenerationError (e.g. timeout) — let it propagate
                returncode, stdout, stderr = await _run_anygif(
                    video_url, start_time, end_time, output_path, proxy=proxy_url
                )
                first_error = None
                logger.info("Attempt 2/2: exited with rc=%d", returncode)
                if stdout:
                    logger.info("Attempt 2/2 stdout: %s", _sanitize_output(stdout))
                if returncode != 0 and stderr:
                    logger.warning("Attempt 2/2 stderr: %s", _sanitize_output(stderr))
            elif first_error:
                raise first_error

        if first_error:
            raise first_error

        if returncode != 0:
            logger.error("All attempts failed (last rc=%d)", returncode)
            raise GifGenerationError("GIF generation failed")

        with open(output_path, "rb") as f:
            data = f.read()

        if not data:
            logger.error("Output file is empty")
            raise GifGenerationError("GIF generation produced empty output")

        file_size_kb = len(data) / 1024
        logger.info("Generation succeeded: output=%.1fKB", file_size_kb)
        return data

    finally:
        try:
            os.unlink(output_path)
        except FileNotFoundError:
            pass
