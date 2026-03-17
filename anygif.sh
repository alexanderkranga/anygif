#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: anygif [options] <url> <start> <end> [WxH] [output]"
  echo ""
  echo "  url      Video URL (any yt-dlp supported site)"
  echo "  start    Start timestamp (mm:ss)"
  echo "  end      End timestamp (mm:ss)"
  echo "  WxH      Output size, e.g. 480x320 (default: max 480px longest side, keeps aspect ratio)"
  echo "  output   Output filename (default: output.mp4)"
  echo ""
  echo "Options:"
  echo "  --fps N      Frames per second (default: 15)"
  echo "  --proxy URL  Route yt-dlp and ffmpeg traffic through an HTTP proxy"
  exit 1
}

FPS=15
PROXY=""

# Parse options
while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --fps)
      FPS="$2"
      if ! [[ "$FPS" =~ ^[0-9]+$ ]] || [ "$FPS" -le 0 ]; then
        echo "Error: fps must be a positive integer"
        exit 1
      fi
      shift 2
      ;;
    --proxy)
      PROXY="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

if [ $# -lt 3 ]; then
  usage
fi

URL="$1"
START="$2"
END="$3"
shift 3

# Parse optional WxH and output
SCALE_FILTER=""
SIZE_LABEL="auto (max 480px)"
if [ $# -gt 0 ] && [[ "$1" == *x* ]]; then
  SIZE="$1"
  WIDTH="${SIZE%%x*}"
  HEIGHT="${SIZE##*x}"
  if ! [[ "$WIDTH" =~ ^[0-9]+$ ]] || ! [[ "$HEIGHT" =~ ^[0-9]+$ ]]; then
    echo "Error: size must be in WxH format (e.g. 480x320)"
    exit 1
  fi
  SCALE_FILTER="scale=${WIDTH}:${HEIGHT}:flags=lanczos"
  SIZE_LABEL="${WIDTH}x${HEIGHT}"
  shift
else
  # Cap longest side at 480px, maintain aspect ratio, never upscale, ensure even dimensions
  SCALE_FILTER="scale='if(gte(iw\,ih)\,min(iw\,480)\,-2)':'if(gte(iw\,ih)\,-2\,min(ih\,480))':flags=lanczos"
fi

OUTPUT="${1:-output.mp4}"

# Convert mm:ss to seconds
to_seconds() {
  local ts="$1"
  local mins="${ts%%:*}"
  local secs="${ts##*:}"
  echo $(( 10#$mins * 60 + 10#$secs ))
}

START_SEC=$(to_seconds "$START")
END_SEC=$(to_seconds "$END")
DURATION=$(( END_SEC - START_SEC ))

if [ "$DURATION" -le 0 ]; then
  echo "Error: end timestamp must be after start timestamp"
  exit 1
fi

YTDLP_PROXY_ARGS=()
if [ -n "$PROXY" ]; then
  YTDLP_PROXY_ARGS=(--proxy "$PROXY")
fi

echo "Downloading and extracting clip..."
echo "  URL:      $URL"
echo "  Range:    $START -> $END (${DURATION}s)"
echo "  Size:     $SIZE_LABEL"
echo "  FPS:      $FPS"
echo "  Proxy:    ${PROXY:-none}"
echo "  Output:   $OUTPUT"

# Default: extract direct URL via yt-dlp, then ffmpeg seeks/trims from it.
# Some platforms (e.g. TikTok) use short-lived signed URLs that expire before
# ffmpeg can fetch them. For those, download the full video first via yt-dlp.

needs_download() {
  case "$URL" in
    *tiktok.com*) return 0 ;;
    *) return 1 ;;
  esac
}

if needs_download; then
  TMPDIR="${TMPDIR:-/tmp}"
  RAW_VIDEO=$(mktemp "${TMPDIR}/anygif_raw_XXXXXX.mp4")
  trap 'rm -f "$RAW_VIDEO"' EXIT

  yt-dlp --no-playlist -f "bv*[height<=720]/bv*" \
    ${YTDLP_PROXY_ARGS[@]+"${YTDLP_PROXY_ARGS[@]}"} -o "$RAW_VIDEO" --force-overwrites "$URL"

  if [ ! -s "$RAW_VIDEO" ]; then
    echo "Error: yt-dlp failed to download video"
    exit 1
  fi

  FFMPEG_INPUT="$RAW_VIDEO"
else
  VIDEO_URL=$(yt-dlp --no-playlist -f "bv*[height<=720]/bv*" \
    ${YTDLP_PROXY_ARGS[@]+"${YTDLP_PROXY_ARGS[@]}"} --get-url "$URL" 2>&1 | grep -E '^https://' | head -1)

  if [ -z "$VIDEO_URL" ]; then
    echo "Error: yt-dlp failed to extract video URL"
    exit 1
  fi

  FFMPEG_INPUT="$VIDEO_URL"
fi

# When proxied, video URLs are often IP-signed to the proxy's IP,
# so ffmpeg must also route through the proxy.
if [ -n "$PROXY" ]; then
  export http_proxy="$PROXY"
  export https_proxy="$PROXY"
fi

ffmpeg -hide_banner -loglevel warning \
  -ss "$START_SEC" -t "$DURATION" \
  -i "$FFMPEG_INPUT" \
  -vf "fps=${FPS},${SCALE_FILTER}" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
  -an -movflags +faststart \
  -y "$OUTPUT"

FILESIZE=$(du -h "$OUTPUT" | cut -f1)
echo "Done! Output: $OUTPUT ($FILESIZE)"
