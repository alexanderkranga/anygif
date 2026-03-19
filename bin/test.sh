#!/usr/bin/env bash
set -euo pipefail

MODE="unit"
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --unit)        MODE="unit";        shift ;;
        --integration) MODE="integration"; shift ;;
        --all)         MODE="all";         shift ;;
        *)             EXTRA_ARGS+=("$1"); shift ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

case "$MODE" in
    unit)
        echo "Running unit tests..."
        exec pytest ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
        ;;
    integration)
        echo "Running integration tests..."
        for tool in yt-dlp ffmpeg; do
            if ! command -v "$tool" &>/dev/null; then
                echo "WARNING: $tool not found in PATH — integration tests will be skipped"
            fi
        done
        exec pytest -m integration --override-ini="addopts=" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
        ;;
    all)
        echo "Running all tests..."
        exec pytest --override-ini="addopts=" ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
        ;;
esac
