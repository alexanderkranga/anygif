"""Tests for the GIF generation module."""

import asyncio
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, call
from app.gif import _add_seconds_to_timestamp, _run_anygif, generate_gif, GifGenerationError


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_subprocess(returncode, stdout=b"", stderr=b"", write_output=None):
    """Create a fake subprocess factory.

    Args:
        returncode: Exit code to return.
        stdout/stderr: Bytes returned by communicate().
        write_output: If provided, bytes written to the output_path arg.
    """
    async def factory(*args, **kwargs):
        if write_output is not None:
            # output_path is the last positional arg
            output_path = args[-1]
            with open(output_path, "wb") as f:
                f.write(write_output)
        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        proc.returncode = returncode
        proc.kill = MagicMock()
        return proc
    return factory


class TestRunAnygif:
    """Tests for the _run_anygif helper."""

    @pytest.mark.asyncio
    async def test_builds_command_without_proxy(self):
        """Without proxy, command has no --proxy flag."""
        calls = []

        async def capture(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=capture):
            await _run_anygif("https://example.com", "0:00", "0:05", "/tmp/out.mp4")

        cmd = calls[0]
        assert cmd == ("anygif", "--fps", "24", "https://example.com", "0:00", "0:05", "/tmp/out.mp4")

    @pytest.mark.asyncio
    async def test_builds_command_with_proxy(self):
        """With proxy, command includes --proxy flag."""
        calls = []

        async def capture(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=capture):
            await _run_anygif(
                "https://example.com", "0:00", "0:05", "/tmp/out.mp4",
                proxy="http://user:pass@gate.decodo.com:7000",
            )

        cmd = calls[0]
        assert cmd == (
            "anygif", "--fps", "24",
            "--proxy", "http://user:pass@gate.decodo.com:7000",
            "https://example.com", "0:00", "0:05", "/tmp/out.mp4",
        )

    @pytest.mark.asyncio
    async def test_timeout_raises_and_kills(self):
        """Timeout kills the process and raises GifGenerationError."""
        async def fake_factory(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.kill = MagicMock()
            return proc

        original_wait_for = asyncio.wait_for

        async def fake_wait_for(coro, *, timeout):
            coro.close()
            raise asyncio.TimeoutError()

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=fake_factory), \
             patch("app.gif.asyncio.wait_for", side_effect=fake_wait_for):
            with pytest.raises(GifGenerationError, match="timed out"):
                await _run_anygif("https://example.com", "0:00", "0:05", "/tmp/out.mp4")


class TestGenerateGif:
    """Tests for the main generate_gif function with retry logic."""

    @pytest.mark.asyncio
    async def test_success_without_proxy(self):
        """Successful on first attempt — no proxy needed."""
        fake_output = b"fake-mp4-data"

        with patch("app.gif._run_anygif", new_callable=AsyncMock) as mock_run, \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            mock_run.return_value = (0, b"Done!", b"")
            # Write the output file when _run_anygif is "called"
            original_side_effect = mock_run.side_effect

            async def write_and_return(*args, **kwargs):
                output_path = args[3]
                with open(output_path, "wb") as f:
                    f.write(fake_output)
                return (0, b"Done!", b"")

            mock_run.side_effect = write_and_return
            result = await generate_gif("https://example.com/video", "1:30", 5)

        assert result == fake_output
        # Only called once — no retry
        assert mock_run.call_count == 1
        # Called without proxy
        assert mock_run.call_args_list[0].kwargs.get("proxy") is None

    @pytest.mark.asyncio
    async def test_retry_with_proxy_on_failure(self):
        """First attempt fails, retries with proxy and succeeds."""
        fake_output = b"fake-mp4-data"
        call_count = 0

        async def mock_run(*args, proxy=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt fails (no proxy)
                assert proxy is None
                return (1, b"", b"ERROR: blocked")
            else:
                # Second attempt with proxy succeeds
                assert proxy == "http://user:pass@gate.decodo.com:7000"
                output_path = args[3]
                with open(output_path, "wb") as f:
                    f.write(fake_output)
                return (0, b"Done!", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://user:pass@gate.decodo.com:7000"):
            result = await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

        assert result == fake_output
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_when_proxy_not_configured(self):
        """First attempt fails and no proxy configured — raises immediately."""
        async def mock_run(*args, proxy=None):
            return (1, b"", b"ERROR: blocked")

        with patch("app.gif._run_anygif", side_effect=mock_run) as mock, \
             patch("app.gif.config.get_proxy_url", return_value=None):
            with pytest.raises(GifGenerationError, match="failed"):
                await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

        # Only one call — no retry without proxy
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_both_attempts_fail(self):
        """Both direct and proxy attempts fail — raises error."""
        call_count = 0

        async def mock_run(*args, proxy=None):
            nonlocal call_count
            call_count += 1
            return (1, b"", b"ERROR: still blocked")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            with pytest.raises(GifGenerationError, match="failed"):
                await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_on_first_attempt_retries_with_proxy(self):
        """Timeout on first attempt triggers proxy retry."""
        fake_output = b"proxy-result"
        call_count = 0

        async def mock_run(*args, proxy=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise GifGenerationError("GIF generation timed out (120s)")
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(fake_output)
            return (0, b"Done!", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            result = await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

        assert result == fake_output
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_timeout_on_both_attempts_raises(self):
        """Timeout on both attempts raises the timeout error."""
        async def mock_run(*args, proxy=None):
            raise GifGenerationError("GIF generation timed out (120s)")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            with pytest.raises(GifGenerationError, match="timed out"):
                await generate_gif("https://youtube.com/watch?v=abc", "0:00", 5)

    @pytest.mark.asyncio
    async def test_empty_output_after_proxy_retry(self):
        """Proxy succeeds (rc=0) but output is empty — raises error."""
        async def mock_run(*args, proxy=None):
            output_path = args[3]
            if proxy:
                with open(output_path, "wb") as f:
                    f.write(b"")  # empty
            return (0 if proxy else 1, b"", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            with pytest.raises(GifGenerationError, match="empty output"):
                await generate_gif("https://example.com/video", "0:00", 5)

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_on_success(self):
        """Temp file is deleted after successful generation."""
        created_paths = []

        async def mock_run(*args, proxy=None):
            output_path = args[3]
            created_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value=None):
            await generate_gif("https://example.com/video", "0:00", 5)

        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_on_error(self):
        """Temp file is deleted even when generation fails."""
        created_paths = []

        async def mock_run(*args, proxy=None):
            output_path = args[3]
            created_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"partial")
            return (1, b"", b"error")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value=None):
            with pytest.raises(GifGenerationError):
                await generate_gif("https://example.com/video", "0:00", 5)

        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_after_proxy_retry_failure(self):
        """Temp file is cleaned up when both attempts fail."""
        created_paths = []

        async def mock_run(*args, proxy=None):
            output_path = args[3]
            if output_path not in created_paths:
                created_paths.append(output_path)
            with open(output_path, "wb") as f:
                f.write(b"partial")
            return (1, b"", b"error")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            with pytest.raises(GifGenerationError):
                await generate_gif("https://example.com/video", "0:00", 5)

        # Same output path used for both attempts
        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])

    @pytest.mark.asyncio
    async def test_proxy_not_used_on_success(self):
        """When first attempt succeeds, proxy is never consulted."""
        async def mock_run(*args, proxy=None):
            assert proxy is None, "Proxy should not be used on success"
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run) as mock, \
             patch("app.gif.config.get_proxy_url") as mock_proxy:
            await generate_gif("https://example.com/video", "0:00", 5)

        assert mock.call_count == 1
        # get_proxy_url should not even be called
        mock_proxy.assert_not_called()
