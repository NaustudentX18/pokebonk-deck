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
say "  script      : $0"

RELEASE_API="https://api.github.com/repos/$REPO/releases/latest"

# --- 1. find the newest asset ------------------------------------------------
say "looking up the latest release…"
RELEASE_JSON="$(curl -fsSL "$RELEASE_API")" || die "could not reach the GitHub API"

ASSET_URL="$(printf '%s' "$RELEASE_JSON" | grep -oE '"browser_download_url": *"[^"]*PokebonkDeck-[0-9][^"]*x86_64\.AppImage"' \
  | head -1 | sed -E 's/.*"([^"]*)"$/\1/' || true)"
[ -n "$ASSET_URL" ] || die "no x86_64 AppImage in the latest release"

VERSION="$(printf '%s' "$RELEASE_JSON" | grep -m1 -oE '"tag_name": *"[^"]+"' | sed -E 's/.*"([^"]+)"/\1/' || true)"
say "  version     : ${VERSION:-unknown}"

# --- 2. expected checksum from latest-linux.yml ------------------------------
# The manifest MUST come from the same release as the asset. Fetching it from
# releases/latest can race with the release pointer and hand back a manifest
# for a different build, which would fail the checksum for no good reason.
[ -n "$VERSION" ] || die "could not determine the release tag"
YML_URL="https://github.com/$REPO/releases/download/$VERSION/latest-linux.yml"
say "fetching the checksum manifest…"
YML="$(curl -fsSL "$YML_URL")" || die "could not fetch latest-linux.yml for $VERSION"
EXPECTED_SHA512="$(printf '%s' "$YML" | grep -A2 "^  - url: .*x86_64\.AppImage$" | grep -m1 '^    sha512:' | sed -E 's/.*sha512: *//' || true)"
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

# --- 5. launch wrapper ------------------------------------------------------
# gamemode gives the CPU governor, I/O priority and core parking that Desktop
# Mode needs. It is NOT used blindly: on the Steam Linux Runtime 3 container
# the wrapper is not on PATH, and a missing binary would break the launch
# entirely. So the wrapper checks and falls back.
LAUNCHER="$INSTALL_DIR/pokebonk-deck-launch.sh"
cat > "$LAUNCHER" <<EOF
#!/bin/sh
# PokéBonk Deck launcher.
# Uses gamemode when it is available; falls back to a plain launch.
APP="$APPIMAGE"
if command -v gamemoderun >/dev/null 2>&1; then
  exec gamemoderun "\$APP" "\$@"
fi
exec "\$APP" "\$@"
EOF
chmod +x "$LAUNCHER"
say "wrote $LAUNCHER"

# --- 6. desktop entry --------------------------------------------------------
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=PokéBonk Deck
Comment=Unofficial native Linux client for the PokéBonk browser game
Exec=$LAUNCHER %U
Icon=$BIN_NAME
Terminal=false
Categories=Game;
StartupWMClass=$BIN_NAME
EOF
chmod +x "$DESKTOP_FILE"
say "wrote $DESKTOP_FILE"

# --- 7. icon -----------------------------------------------------------------
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
mkdir -p "$ICON_DIR"
ICON_URL="$(printf '%s' "$RELEASE_JSON" | grep -oE '"browser_download_url": *"[^"]*pokebonk-deck-icon\.png"' \
  | head -1 | sed -E 's/.*"([^"]*)"$/\1/' || true)"
if [ -n "$ICON_URL" ]; then
  curl -fsSL -o "$ICON_DIR/$BIN_NAME.png" "$ICON_URL" \
    && say "installed the launcher icon" \
    || warn "could not fetch the icon (not fatal)"
else
  warn "no icon asset in the release (not fatal)"
fi

# --- 8. Steam integration ----------------------------------------------------
# Adds the game to the Steam library so it shows up in Game Mode, with the
# controller enabled, the Deck's native resolution and the gamemode launch
# option applied.
# The helper must come from the SAME release as the app: releases/latest can
# still point at the previous release for a while after a new one is published.
STEAM_TOOL_URL=""
STEAM_TOOL="$INSTALL_DIR/steam_integration.py"

STEAM_WAS_RUNNING=0
if pgrep -x steam >/dev/null 2>&1 || pgrep -x steamwebhelper >/dev/null 2>&1; then
  STEAM_WAS_RUNNING=1
  warn "the Steam client is running — it rewrites shortcuts.vdf on exit."
  warn "quit Steam (steam -shutdown) and re-run this, or restart the client afterwards."
fi

say "adding it to Steam (so it appears in Game Mode)…"
STEAM_OK=0
STEAM_TOOL_URL="https://github.com/$REPO/releases/download/$VERSION/steam_integration.py"
ARTWORK_DIR="$INSTALL_DIR/artwork"
ARTWORK_BASE="https://github.com/$REPO/releases/download/$VERSION"
if command -v python3 >/dev/null; then
  curl -fsSL -o "$STEAM_TOOL" "$STEAM_TOOL_URL" 2>/dev/null || true
  if [ -s "$STEAM_TOOL" ]; then
    # The Steam library art, so the entry is not a blank tile.
    mkdir -p "$ARTWORK_DIR"
    for art in library_hero.jpg library_capsule.jpg capsule.jpg capsulev5.jpg \
                header.jpg logo.png icon.jpg; do
      curl -fsSL -o "$ARTWORK_DIR/$art" "$ARTWORK_BASE/$art" 2>/dev/null || true
    done

    if python3 "$STEAM_TOOL" --exe "$APPIMAGE" --name "PokéBonk Deck" \
         --launcher "$LAUNCHER" --resolution "1280x800" --artwork "$ARTWORK_DIR" \
         > "$INSTALL_DIR/steam-setup.log" 2>&1; then
      STEAM_OK=1
      say "Steam is set up — the game is in your library and in Game Mode"
    else
      warn "Steam was not set up (details: $INSTALL_DIR/steam-setup.log)"
      warn "add it by hand: Library -> Add a Non-Steam Game -> $APPIMAGE"
    fi
    sed 's/^/    /' "$INSTALL_DIR/steam-setup.log" 2>/dev/null || true
  else
    warn "could not fetch the Steam integration helper"
  fi
else
  warn "python3 is not available, skipping the Steam integration"
  warn "add it by hand: Library -> Add a Non-Steam Game -> $APPIMAGE"
fi

if [ "$STEAM_WAS_RUNNING" = "1" ]; then
  cat <<'EOF'

*** Quit and reopen Steam now. ***
The client reads shortcuts.vdf only when it starts, so the settings just
written (the overlay switch, the icon, the layout) are not live until the
client restarts. Until then the game will still hang on the loading screen.
EOF
fi

cat <<EOF

$(say "done")

Play it now:
  $APPIMAGE

The client checks pokebonk.com for new game builds on launch and reloads itself
when the upstream game updates.

To uninstall:
  rm -rf "$INSTALL_DIR" "$DESKTOP_FILE" "$ICON_DIR/$BIN_NAME.png"
EOF

if [ "$STEAM_OK" = "1" ]; then
  cat <<'EOF'

In Steam: it is in your library as "PokéBonk Deck" — start it from Game Mode
with the Deck's controller. Steam Input is set to the gamepad layout, the
resolution is pinned to 1280x800, and the launch goes through a wrapper that
uses gamemode when it is available.
EOF
fi
