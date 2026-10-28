#!/usr/bin/env bash
# Remove the PokéBonk Deck client completely, leaving the machine as it was
# before the installer ran — so a fresh install can be tested end to end.
#
#   curl -fsSL https://github.com/NaustudentX18/pokebonk-deck/releases/latest/download/uninstall.sh | bash
#
# Everything it removes is listed first; pass --dry-run to see and stop.
set -euo pipefail

REPO="NaustudentX18/pokebonk-deck"
TOOL_URL="https://github.com/$REPO/releases/latest/download/uninstall.py"
TOOL="${TMPDIR:-/tmp}/pokebonk-deck-uninstall.py"

command -v python3 >/dev/null || {
  printf 'python3 is required\n' >&2
  exit 1
}

curl -fsSL -o "$TOOL" "$TOOL_URL" || {
  printf 'could not fetch the uninstaller\n' >&2
  exit 1
}

python3 "$TOOL" "$@"
rm -f "$TOOL"
