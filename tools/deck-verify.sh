#!/usr/bin/env bash
# PokéBonk Deck — one-shot verification on a Steam Deck.
# Run this IN THE DECK'S DESKTOP MODE TERMINAL and paste the whole output back.
#   bash deck-verify.sh
# Nothing here installs anything or changes settings.
set -uo pipefail

# Everything printed from here on is also written to a file, so the report can
# be posted back at the end without re-running anything.
REPORT_FILE="${POKEBONK_REPORT_FILE:-/tmp/pokebonk-deck-report.txt}"
exec > >(tee "$REPORT_FILE")
trap 'exec 1>&- 2>&-; wait' EXIT

line() { printf '\n\033[1;36m── %s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

line "1. System"
cat /etc/os-release 2>/dev/null | grep -E '^(PRETTY_NAME|BUILD_ID)=' || echo "  (no os-release)"
printf '  kernel: %s\n' "$(uname -r)"
printf '  arch:   %s\n' "$(uname -m)"

line "2. User namespaces (Electron sandbox prerequisite)"
if [ -f /proc/sys/kernel/unprivileged_userns_clone ]; then
  v=$(cat /proc/sys/kernel/unprivileged_userns_clone)
  [ "$v" = "1" ] && ok "unprivileged_userns_clone=1 — Chromium sandbox works" \
                  || bad "unprivileged_userns_clone=$v — Chromium will need --no-sandbox"
else
  warn "sysctl not exposed on this kernel"
fi
if unshare -Ur true 2>/dev/null; then ok "unshare -Ur works"; else warn "unshare -Ur failed"; fi

line "3. Graphics stack"
if command -v glxinfo >/dev/null; then
  glxinfo -B 2>/dev/null | grep -E 'OpenGL renderer|OpenGL version' | sed 's/^/  /' \
    || warn "glxinfo produced no output"
else
  warn "glxinfo not installed (mesa-utils) — checking /dev/dri instead"
fi
ls -l /dev/dri 2>/dev/null | sed 's/^/  /' || bad "no /dev/dri — no GPU access"

line "4. Gamepad: joydev nodes (Chromium on Linux REQUIRES /dev/input/js*)"
if ls /dev/input/js* >/dev/null 2>&1; then
  ls -l /dev/input/js* | sed 's/^/  /'
  ok "joydev node(s) present"
else
  bad "no /dev/input/js* — Chromium cannot enumerate a gamepad"
fi
echo "  -- udev properties of the first js node --"
first_js=$(ls /dev/input/js* 2>/dev/null | head -1)
if [ -n "$first_js" ]; then
  udevadm info -q property -n "$first_js" 2>/dev/null \
    | grep -E 'ID_INPUT_JOYSTICK|ID_INPUT=|NAME|PRODUCT' | sed 's/^/  /' \
    || warn "udevadm could not read $first_js"
  # Chromium needs ID_INPUT_JOYSTICK=1 and read access on the node.
  mode=$(stat -c '%a %U:%G' "$first_js" 2>/dev/null)
  echo "  mode/owner: $mode"
  case "$mode" in
    6*|4*) ok "joydev is world/group readable" ;;
    *)     warn "joydev is $mode — if Chromium cannot open it, see the udev note in docs/troubleshooting.md" ;;
  esac
fi
echo "  -- all input devices --"
ls /dev/input/ 2>/dev/null | sed 's/^/  /'

line "5. udev + container visibility (matters when launched from Steam)"
if [ -d /run/udev ]; then ok "/run/udev present — libudev enumeration works"; else bad "/run/udev MISSING — Chromium dlopens libudev; if the app runs inside the Steam Linux Runtime this is the usual cause of 'no controller'"; fi
if [ -n "${FLATPAK_ID:-}" ]; then warn "running inside Flatpak ($FLATPAK_ID) — flatpak override --device=input --filesystem=/run/udev:ro <app-id> may be required"; fi
if [ -n "${STEAM_RUNTIME_PID:-}" ] || [ -d /usr/share/steam-runtime ]; then warn "Steam Linux Runtime present — check /dev/input and /run/udev inside the container"; fi

line "6. Steam Input action set"
if command -v steam >/dev/null; then
  ok "steam client present"
else
  warn "steam CLI not in PATH (normal on SteamOS outside the container)"
fi
echo "  Reminder: Steam Input cannot be disabled for the Deck's built-in controller."
echo "  Use the GAMEPAD action set (not Desktop Layout) and run in Game Mode."

line "7. AppImage prerequisites"
# Cache ldconfig output first: `ldconfig -p | grep -q` dies from SIGPIPE under
# `set -o pipefail` and would report every library as missing.
ldc="$(ldconfig -p 2>/dev/null)"
for lib in libnss3.so libatk-1.0.so.0 libgbm.so.1 libasound.so.2 libcups.so.2 libdrm.so.2 libxkbcommon.so.0 libgtk-3.so.0; do
  if printf '%s' "$ldc" | grep -F "$lib" >/dev/null; then ok "$lib"; else bad "$lib MISSING"; fi
done

line "8. The client itself"
APPIMAGE="${POKEBONK_APPIMAGE:-$HOME/.local/share/pokebonk-deck/pokebonk-deck.AppImage}"
if [ -x "$APPIMAGE" ]; then
  echo "  running the client self-test: $APPIMAGE"
  SELFTEST="$(timeout 120 "$APPIMAGE" --selftest --screenshot /tmp/pokebonk-deck-window.png 2>&1 | grep -E 'SELFTEST_JSON' | head -1)"
  if [ -n "$SELFTEST" ]; then
    echo "  ${SELFTEST#SELFTEST_JSON }"
    if [ -f /tmp/pokebonk-deck-window.png ]; then
      echo "  captured what the app is showing: /tmp/pokebonk-deck-window.png"
    fi
  else
    echo "  ! the self-test produced no result (run it by hand for the error)"
  fi
else
  echo "  ! client not found at $APPIMAGE — install it first"
fi

line "9. Summary"
echo "  Copy everything above back to the agent — especially section 4."

# --- report back automatically ------------------------------------------------
# If a collector is reachable, send the whole report there so nobody has to
# copy and paste it.
TARGETS=()
[ -n "${POKEBONK_REPORT_URL:-}" ] && TARGETS+=("$POKEBONK_REPORT_URL")
TARGETS+=("http://100.105.91.3:8100/report" "http://192.168.4.220:8100/report")

SENT=0
for url in "${TARGETS[@]}"; do
  if command -v curl >/dev/null; then
    sleep 0.2
    if curl -fsS --max-time 4 -X POST --data-binary @"$REPORT_FILE" "$url" >/dev/null 2>&1; then
      echo "  report sent to $url"
      SENT=1
      break
    fi
  fi
done

if [ "$SENT" = "0" ]; then
  echo "  (could not reach report collector — copy this output instead)"
fi
