#!/usr/bin/env bash
# Build site media from real captures.
#   tools/build-media.sh <title.png> <partners.png> <hub.png> <league.png> <gameplay.png> <gameplay.webm>
set -euo pipefail
SITE="$(cd "$(dirname "$0")/.." && pwd)/site"
MEDIA="$SITE/media"
mkdir -p "$MEDIA"

TITLE="${1:?title png}"; PARTNERS="${2:?partners png}"; HUB="${3:?hub png}"
LEAGUE="${4:?league png}"; GAMEPLAY="${5:?gameplay png}"; WEBM="${6:?gameplay webm}"

say() { printf '\033[1;36m[media]\033[0m %s\n' "$*"; }

still() {
  local src="$1" name="$2" width="${3:-1600}"
  [ -f "$src" ] || { say "MISSING $src"; return 1; }
  magick "$src" -resize "${width}x" -strip -quality 90 "$MEDIA/$name.png"
  magick "$src" -resize "${width}x" -strip -quality 84 "$MEDIA/$name.webp"
  say "$name  $(magick identify -format '%wx%h' "$MEDIA/$name.png")  $(du -h "$MEDIA/$name.png" | cut -f1)"
}

still "$TITLE"    "01-title"
still "$PARTNERS" "02-partners"
still "$HUB"      "03-hub"
still "$LEAGUE"   "04-league"
still "$GAMEPLAY" "05-gameplay"

say "encoding video…"
ffmpeg -y -hide_banner -loglevel error -i "$WEBM" \
  -vf "scale=1280:-2:flags=lanczos,format=yuv420p" \
  -c:v libx264 -preset slow -crf 22 -movflags +faststart \
  "$MEDIA/gameplay.mp4"
cp "$WEBM" "$MEDIA/gameplay.webm"
ffmpeg -y -hide_banner -loglevel error -ss 3 -i "$MEDIA/gameplay.mp4" \
  -frames:v 1 -q:v 3 "$MEDIA/gameplay-poster.jpg"
say "gameplay.mp4 $(du -h "$MEDIA/gameplay.mp4" | cut -f1)  poster $(magick identify -format '%wx%h' "$MEDIA/gameplay-poster.jpg")"
say "done -> $MEDIA"
