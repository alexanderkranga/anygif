"""Tests for the GIF generation module."""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.gif import _add_seconds_to_timestamp, generate_gif, GifGenerationError


class TestAddSecondsToTimestamp:
    def test_simple_addition(self):
        assert _add_seconds_to_timestamp("1:30", 5) == "1:35"

    def test_minute_overflow(self):
        assert _add_seconds_to_timestamp("1:55", 10) == "2:05"

    def test_from_zero(self):
        assert _add_seconds_to_timestamp("0:00", 10) == "0:10"

    def test_large_minutes(self):
        assert _add_seconds_to_timestamp("59:50", 15) == "60:05"

    def test_exact_minute(self):
        assert _add_seconds_to_timestamp("1:50", 10) == "2:00"


class TestGenerateGif:
    @pytest.mark.asyncio
    async def test_successful_generation(self, tmp_path):
        """Successful subprocess run returns file bytes."""
        fake_output = b"fake-mp4-data"

        async def fake_create_subprocess_exec(*args, **kwargs):
            # Write fake output to the path (last positional arg before output)
            output_path = args[6]  # anygif --fps 24 url start end OUTPUT
            with open(output_path, "wb") as f:
                f.write(fake_output)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"Done!", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            result = await generate_gif("https://example.com/video", "1:30", 5)

        assert result == fake_output

    @pytest.mark.asyncio
    async def test_nonzero_exit_raises(self):
        """Non-zero exit code raises GifGenerationError."""
        async def fake_create_subprocess_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b"ERROR: bot check failed"))
            proc.returncode = 1
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            with pytest.raises(GifGenerationError, match="failed"):
                await generate_gif("https://example.com/video", "0:00", 5)

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        """Timeout raises GifGenerationError and kills the process."""
        async def fake_create_subprocess_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.kill = MagicMock()
            return proc

        original_wait_for = asyncio.wait_for
        call_count = 0

        async def fake_wait_for(coro, *, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Cancel the coroutine to avoid "was never awaited" warning
                coro.close()
                raise asyncio.TimeoutError()
            return await original_wait_for(coro, timeout=timeout)

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec), \
             patch("app.gif.asyncio.wait_for", side_effect=fake_wait_for):
            with pytest.raises(GifGenerationError, match="timed out"):
                await generate_gif("https://example.com/video", "0:00", 5)

    @pytest.mark.asyncio
    async def test_empty_output_raises(self, tmp_path):
        """Empty output file raises GifGenerationError."""
        async def fake_create_subprocess_exec(*args, **kwargs):
            output_path = args[6]
            with open(output_path, "wb") as f:
                f.write(b"")  # empty file
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"Done!", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            with pytest.raises(GifGenerationError, match="empty output"):
                await generate_gif("https://example.com/video", "0:00", 5)

    @pytest.mark.asyncio
    async def test_bot_detection_error_raises(self):
        """Bot detection errors from yt-dlp raise GifGenerationError without leaking stderr."""
        error_msg = "ERROR: [youtube] Sign in to confirm you're not a bot"

        async def fake_create_subprocess_exec(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", error_msg.encode()))
            proc.returncode = 1
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            with pytest.raises(GifGenerationError, match="failed"):
                await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_on_success(self, tmp_path):
        """Temp file is deleted after successful generation."""
        import os

        created_paths = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            output_path = args[6]
            created_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"data")
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            await generate_gif("https://example.com/video", "0:00", 5)

        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_on_error(self):
        """Temp file is deleted even when generation fails."""
        import os

        created_paths = []

        async def fake_create_subprocess_exec(*args, **kwargs):
            output_path = args[6]
            created_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"partial")
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error"))
            proc.returncode = 1
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
            with pytest.raises(GifGenerationError):
                await generate_gif("https://example.com/video", "0:00", 5)

        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])
