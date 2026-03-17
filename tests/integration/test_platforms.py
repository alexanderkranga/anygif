"""Integration tests — generate real clips from each supported platform."""

import pytest
from app.gif import generate_gif

PLATFORM_PARAMS = [
    pytest.param("https://www.youtube.com/watch?v=jNQXAC9IVRw", "0:05", 3, id="youtube"),
    pytest.param("https://x.com/i/status/2033893383417282750", "0:00", 3, id="twitter"),
    pytest.param("https://vimeo.com/76979871", "0:05", 3, id="vimeo"),
    pytest.param("https://www.dailymotion.com/video/x5e9eog", "0:10", 3, id="dailymotion"),
    pytest.param("https://streamable.com/moo", "0:00", 3, id="streamable"),
    pytest.param("https://www.tiktok.com/@scout2015/video/6718335390845095173", "0:00", 3, id="tiktok"),
    pytest.param("https://i.imgur.com/A61SaA1.mp4", "0:00", 3, id="imgur"),
]


@pytest.mark.integration
class TestPlatforms:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("url, start_time, duration", PLATFORM_PARAMS)
    async def test_generate_clip(self, url, start_time, duration):
        data = await generate_gif(url, start_time, duration)
        assert len(data) > 1000, f"output too small ({len(data)} bytes)"
        assert len(data) < 50_000_000, f"output exceeds 50MB ({len(data)} bytes)"
        assert data[4:8] == b"ftyp", f"not a valid MP4 container (got {data[:8]!r})"
