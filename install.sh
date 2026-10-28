#!/usr/bin/env bash
# PokéBonk Deck — installer.
#
#   curl -fsSL https://raw.githubusercontent.com/NaustudentX18/pokebonk-deck/main/install.sh | bash
#
# Downloads the latest AppImage, verifies it against the published sha512,
# installs it to ~/.local/share/pokebonk-deck, writes a .desktop entry and
# prints what to do next. Safe to re-run: it upgrades in place.
set -euo pipefail

REPO="NaustudentX18/pokebonk-deck"
INSTALL_DIR="${POKEBONK_DECK_DIR:-$HOME/.local/share/pokebonk-deck}"
BIN_NAME="pokebonk-deck"
APPIMAGE="$INSTALL_DIR/$BIN_NAME.AppImage"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/gg.pokebonk.deck.desktop"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31mx\033[0m %s\n' "$*" >&2; exit 1; }

command -v curl >/dev/null || die "curl is required"

case "$(uname -m)" in
  x86_64|amd64) ARCH="x86_64" ;;
  *) die "Only x86_64 is supported (this is $(uname -m))" ;;
esac

say "PokéBonk Deck installer"
say "  install dir : $INSTALL_DIR"

RELEASE_API="https://api.github.com/repos/$REPO/releases/latest"
YML_URL="https://github.com/$REPO/releases/latest/download/latest-linux.yml"

# --- 1. find the newest asset ------------------------------------------------
say "looking up the latest release…"
RELEASE_JSON="$(curl -fsSL "$RELEASE_API")" || die "could not reach the GitHub API"

ASSET_URL="$(printf '%s' "$RELEASE_JSON" | grep -oE '"browser_download_url": *"[^"]*PokebonkDeck-[0-9][^"]*x86_64\.AppImage"' \
  | head -1 | sed -E 's/.*"([^"]*)"$/\1/')"
[ -n "$ASSET_URL" ] || die "no x86_64 AppImage in the latest release"

VERSION="$(printf '%s' "$RELEASE_JSON" | grep -m1 -oE '"tag_name": *"[^"]+"' | sed -E 's/.*"([^"]+)"/\1/')"
say "  version     : ${VERSION:-unknown}"

# --- 2. expected checksum from latest-linux.yml ------------------------------
say "fetching the checksum manifest…"
YML="$(curl -fsSL "$YML_URL")" || die "could not fetch latest-linux.yml"
EXPECTED_SHA512="$(printf '%s' "$YML" | grep -A2 "^  - url: .*x86_64\.AppImage$" | grep -m1 '^    sha512:' | sed -E 's/.*sha512: *//')"
[ -n "$EXPECTED_SHA512" ] || die "no sha512 for the AppImage in latest-linux.yml"

# --- 3. download -------------------------------------------------------------
mkdir -p "$INSTALL_DIR"
TMP="$INSTALL_DIR/.download.$$"
say "downloading…"
curl -fL --progress-bar -o "$TMP" "$ASSET_URL" || { rm -f "$TMP"; die "download failed"; }

say "verifying sha512…"
# latest-linux.yml carries the digest base64-encoded, which is what
# electron-updater itself compares against. sha512sum prints hex, so
# convert rather than comparing the two directly.
sha512_b64() {
  if command -v openssl >/dev/null; then
    openssl dgst -sha512 -binary "$1" | base64 | tr -d '\n'
  else
    sha512sum "$1" | cut -d' ' -f1 | xxd -r -p | base64 | tr -d '\n'
  fi
}
ACTUAL_SHA512="$(sha512_b64 "$TMP")"
if [ "$ACTUAL_SHA512" != "$EXPECTED_SHA512" ]; then
  rm -f "$TMP"
  die "checksum mismatch — refusing to install"
fi
say "  checksum ok"

# --- 4. install --------------------------------------------------------------
# Replace in place: the app's own self-updater rewrites this same path, so it
# must stay on one filesystem (a FAT32 SD card cannot be renamed across).
if [ -f "$APPIMAGE" ]; then
  rm -f "$APPIMAGE.old"
  mv "$APPIMAGE" "$APPIMAGE.old"
fi
mv "$TMP" "$APPIMAGE"
chmod +x "$APPIMAGE"
rm -f "$APPIMAGE.old"
say "installed $APPIMAGE"

# --- 5. desktop entry --------------------------------------------------------
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PokéBonk Deck
Comment=Unofficial native Linux client for the PokéBonk browser game
Exec=$APPIMAGE %U
Icon=$BIN_NAME
Terminal=false
Categories=Game;
StartupWMClass=$BIN_NAME
EOF
chmod +x "$DESKTOP_FILE"
say "wrote $DESKTOP_FILE"

# --- 6. icon -----------------------------------------------------------------
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DIR"
ICON_URL="$(printf '%s' "$RELEASE_JSON" | grep -oE '"browser_download_url": *"[^"]*pokebonk-deck-icon\.png"' \
  | head -1 | sed -E 's/.*"([^"]*)"$/\1/')"
if [ -n "$ICON_URL" ]; then
  curl -fsSL -o "$ICON_DIR/$BIN_NAME.png" "$ICON_URL" \
    && say "installed the launcher icon" \
    || warn "could not fetch the icon (not fatal)"
else
  warn "no icon asset in the release (not fatal)"
fi

cat <<EOF

$(say "done")

Play it now:
  $APPIMAGE

Or add it to Steam: Library -> Add a Non-Steam Game -> pick
  $APPIMAGE
and set the launch option to
  gamemoderun %command%

The app checks pokebonk.com for new game builds on launch and reloads
itself when the upstream game updates.

To uninstall:
  rm -rf "$INSTALL_DIR" "$DESKTOP_FILE"
EOF
