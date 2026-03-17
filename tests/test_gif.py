"""Tests for the GIF generation module."""

import asyncio
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.gif import (
    _add_seconds_to_timestamp,
    _run_anygif,
    _sanitize_output,
    generate_gif,
    GifGenerationError,
)


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


class TestSanitizeOutput:
    def test_strips_http_urls(self):
        raw = b"ERROR: unable to download http://example.com/video.mp4 forbidden"
        result = _sanitize_output(raw)
        assert "example.com" not in result
        assert "<URL>" in result
        assert "ERROR: unable to download" in result

    def test_strips_https_urls(self):
        raw = b"Downloading https://rr1---sn-abc.googlevideo.com/videoplayback?key=xyz"
        result = _sanitize_output(raw)
        assert "googlevideo" not in result
        assert "<URL>" in result

    def test_strips_proxy_urls(self):
        raw = b"Using proxy http://user:secret@gate.decodo.com:7000"
        result = _sanitize_output(raw)
        assert "secret" not in result
        assert "decodo" not in result
        assert "<URL>" in result

    def test_strips_multiple_urls(self):
        raw = b"Tried https://a.com/1 and https://b.com/2 both failed"
        result = _sanitize_output(raw)
        assert "a.com" not in result
        assert "b.com" not in result
        assert result.count("<URL>") == 2

    def test_preserves_non_url_text(self):
        raw = b"ERROR: Sign in to confirm you're not a bot"
        assert _sanitize_output(raw) == "ERROR: Sign in to confirm you're not a bot"

    def test_truncates_long_output(self):
        raw = b"x" * 3000
        result = _sanitize_output(raw, max_len=100)
        assert len(result) < 200
        assert "truncated" in result

    def test_handles_empty_output(self):
        assert _sanitize_output(b"") == ""

    def test_handles_binary_garbage(self):
        raw = b"\xff\xfe\x00\x01 some text"
        result = _sanitize_output(raw)
        assert "some text" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_subprocess(returncode, stdout=b"", stderr=b"", write_output=None):
    """Create a fake subprocess factory."""
    async def factory(*args, **kwargs):
        if write_output is not None:
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
        calls = []

        async def capture(*args, **kwargs):
            calls.append(args)
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.returncode = 0
            return proc

        with patch("app.gif.asyncio.create_subprocess_exec", side_effect=capture):
            await _run_anygif("https://example.com", "0:00", "0:05", "/tmp/out.mp4")

        assert calls[0] == ("anygif", "--fps", "24", "https://example.com", "0:00", "0:05", "/tmp/out.mp4")

    @pytest.mark.asyncio
    async def test_builds_command_with_proxy(self):
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

        assert calls[0] == (
            "anygif", "--fps", "24",
            "--proxy", "http://user:pass@gate.decodo.com:7000",
            "https://example.com", "0:00", "0:05", "/tmp/out.mp4",
        )

    @pytest.mark.asyncio
    async def test_timeout_raises_and_kills(self):
        async def fake_factory(*args, **kwargs):
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b""))
            proc.kill = MagicMock()
            return proc

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

        async def write_and_return(*args, proxy=None):
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(fake_output)
            return (0, b"Done!", b"")

        with patch("app.gif._run_anygif", side_effect=write_and_return) as mock_run, \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            result = await generate_gif("https://example.com/video", "1:30", 5)

        assert result == fake_output
        assert mock_run.call_count == 1
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
                assert proxy is None
                return (1, b"", b"ERROR: Sign in to confirm you're not a bot")
            else:
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
                    f.write(b"")
            return (0 if proxy else 1, b"", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            with pytest.raises(GifGenerationError, match="empty output"):
                await generate_gif("https://example.com/video", "0:00", 5)

    @pytest.mark.asyncio
    async def test_cleans_up_temp_file_on_success(self):
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

        assert len(created_paths) == 1
        assert not os.path.exists(created_paths[0])

    @pytest.mark.asyncio
    async def test_proxy_not_used_on_success(self):
        """When first attempt succeeds, _run_anygif is called once without proxy."""
        async def mock_run(*args, proxy=None):
            assert proxy is None, "Proxy should not be passed on successful first attempt"
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"", b"")

        with patch("app.gif._run_anygif", side_effect=mock_run) as mock, \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            await generate_gif("https://example.com/video", "0:00", 5)

        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_logs_do_not_contain_urls(self, caplog):
        """Ensure no video or proxy URLs appear in log output."""
        video_url = "https://youtube.com/watch?v=secret123"
        proxy_url = "http://user:pass@gate.decodo.com:7000"
        call_count = 0

        async def mock_run(*args, proxy=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (1, b"Downloading https://rr1.googlevideo.com/xyz", b"ERROR: https://youtube.com/fail")
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"Done! Output: https://cdn.example.com/vid.mp4", b"")

        import logging
        with caplog.at_level(logging.DEBUG, logger="app.gif"), \
             patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value=proxy_url):
            await generate_gif(video_url, "0:00", 5)

        all_logs = caplog.text
        assert "secret123" not in all_logs
        assert "youtube.com" not in all_logs
        assert "googlevideo" not in all_logs
        assert "decodo" not in all_logs
        assert "user:pass" not in all_logs
        assert "cdn.example.com" not in all_logs

    @pytest.mark.asyncio
    async def test_logs_contain_useful_diagnostics(self, caplog):
        """Logs include attempt numbers, return codes, and timing info."""
        async def mock_run(*args, proxy=None):
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"Done!", b"")

        import logging
        with caplog.at_level(logging.DEBUG, logger="app.gif"), \
             patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value=None):
            await generate_gif("https://example.com/video", "1:30", 5)

        all_logs = caplog.text
        assert "start=1:30" in all_logs
        assert "end=1:35" in all_logs
        assert "duration=5s" in all_logs
        assert "Attempt 1/2" in all_logs
        assert "rc=0" in all_logs
        assert "succeeded" in all_logs

    @pytest.mark.asyncio
    async def test_logs_on_retry_path(self, caplog):
        """Logs show both attempts when retry happens."""
        call_count = 0

        async def mock_run(*args, proxy=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (1, b"", b"ERROR: bot check")
            output_path = args[3]
            with open(output_path, "wb") as f:
                f.write(b"data")
            return (0, b"Done!", b"")

        import logging
        with caplog.at_level(logging.DEBUG, logger="app.gif"), \
             patch("app.gif._run_anygif", side_effect=mock_run), \
             patch("app.gif.config.get_proxy_url", return_value="http://proxy:7000"):
            await generate_gif("https://example.com/video", "0:00", 5)

        all_logs = caplog.text
        assert "Attempt 1/2: direct" in all_logs
        assert "Attempt 1/2: exited with rc=1" in all_logs
        assert "Attempt 1/2 stderr" in all_logs
        assert "bot check" in all_logs
        assert "Attempt 2/2: retrying with proxy" in all_logs
        assert "Attempt 2/2: exited with rc=0" in all_logs
        assert "succeeded" in all_logs
