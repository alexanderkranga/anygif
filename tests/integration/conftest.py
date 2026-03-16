"""Integration test fixtures — ensure anygif is on PATH, skip if tools missing."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ANYGIF_SCRIPT = REPO_ROOT / "anygif.sh"


def pytest_collection_modifyitems(config, items):
    """Skip all integration tests if yt-dlp or ffmpeg are not installed."""
    missing = []
    for tool in ("yt-dlp", "ffmpeg"):
        if shutil.which(tool) is None:
            missing.append(tool)
    if missing:
        skip = pytest.mark.skip(reason=f"missing required tools: {', '.join(missing)}")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip)


@pytest.fixture(autouse=True, scope="session")
def anygif_on_path():
    """Symlink anygif.sh → anygif in a temp dir and prepend to PATH."""
    tmpdir = tempfile.mkdtemp(prefix="anygif-test-")
    link = os.path.join(tmpdir, "anygif")
    os.symlink(str(ANYGIF_SCRIPT), link)
    os.chmod(link, 0o755)

    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{tmpdir}:{old_path}"
    yield
    os.environ["PATH"] = old_path
    os.unlink(link)
    os.rmdir(tmpdir)
