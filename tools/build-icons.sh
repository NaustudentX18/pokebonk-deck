#!/usr/bin/env bash
# Generate the app icon set from assets/icon.svg.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p assets
magick -background none assets/icon.svg -resize 512x512 assets/icon.png
magick -background none assets/icon.svg -resize 256x256 assets/icon-256.png
magick -background none assets/icon.svg -resize 128x128 assets/icon-128.png
magick -background none assets/icon.svg -resize 64x64 assets/icon-64.png
echo "icons written:"
ls -la assets/
