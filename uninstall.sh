#!/usr/bin/env bash
# Remove the PokéBonk Deck client completely, leaving the machine as it was
# before the installer ran — so a fresh install can be tested end to end.
#
#   curl -fsSL https://github.com/NaustudentX18/pokebonk-deck/releases/latest/download/uninstall.sh | bash
#
# Everything it removes is listed first; pass --dry-run to see and stop.
set -euo pipefail

REPO="NaustudentX18/pokebonk-deck"
BASE="https://github.com/$REPO/releases/latest/download"
WORK="${TMPDIR:-/tmp}/pokebonk-deck-uninstall"
UNINSTALLER="$WORK/uninstall.py"

command -v python3 >/dev/null || {
  printf 'python3 is required\n' >&2
  exit 1
}

rm -rf "$WORK" && mkdir -p "$WORK"

# The uninstaller is self-contained: one file, nothing beside it.
curl -fsSL -o "$UNINSTALLER" "$BASE/uninstall.py" || {
  printf 'could not fetch the uninstaller\n' >&2
  exit 1
}

python3 "$UNINSTALLER" "$@"
rm -rf "$WORK"
