"""Async wrapper around anygif.sh for GIF generation."""

import asyncio
import os
import uuid
import logging

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


async def generate_gif(video_url: str, start_time: str, duration: int) -> bytes:
    """Run anygif to generate a GIF and return the bytes."""
    end_time = _add_seconds_to_timestamp(start_time, duration)
    output_path = f"/tmp/{uuid.uuid4()}.mp4"

    try:
        proc = await asyncio.create_subprocess_exec(
            "anygif", "--fps", "24", video_url, start_time, end_time, output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise GifGenerationError("GIF generation timed out (120s)")

        stdout_str = stdout.decode(errors="replace").strip()
        stderr_str = stderr.decode(errors="replace").strip()

        # Always log stdout (contains debug info from anygif.sh)
        if stdout_str:
            logger.info("anygif stdout:\n%s", stdout_str)
        if stderr_str:
            logger.info("anygif stderr:\n%s", stderr_str)

        if proc.returncode != 0:
            detail = stderr_str or stdout_str
            logger.error("anygif failed (rc=%d): %s", proc.returncode, detail)
            raise GifGenerationError(f"GIF generation failed: {detail}")

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
