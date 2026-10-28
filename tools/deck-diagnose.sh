#!/usr/bin/env bash
# PokéBonk Deck — diagnose why the game does not start in Game Mode.
#
#   bash deck-diagnose.sh
#
# Captures the installed client, the Steam shortcut as Steam sees it, the
# launch through Steam's own wrapper (which is what injects the overlay), the
# kernel log and the Steam client's own log, then posts the lot to the
# collector.
set -uo pipefail

REPORT_FILE="${POKEBONK_REPORT_FILE:-/tmp/pokebonk-deck-diagnose.txt}"
exec > >(tee "$REPORT_FILE")
trap 'exec 1>&- 2>&-; wait' EXIT

INSTALL_DIR="$HOME/.local/share/pokebonk-deck"
APPIMAGE="$INSTALL_DIR/pokebonk-deck.AppImage"
LAUNCHER="$INSTALL_DIR/pokebonk-deck-launch.sh"
STEAM_ROOT="$HOME/.local/share/Steam"
[ -d "$STEAM_ROOT" ] || STEAM_ROOT="$HOME/.steam/steam"

line() { printf '\n\033[1;36m── %s\033[0m\n' "$1"; }

line "1. The installed client"
ls -la "$INSTALL_DIR" 2>/dev/null || echo "  ! nothing installed at $INSTALL_DIR"
if [ -x "$APPIMAGE" ]; then
  "$APPIMAGE" --appimage-version 2>/dev/null | head -1
fi
cat "$INSTALL_DIR/steam-setup.log" 2>/dev/null | sed 's/^/  /' | tail -15

line "2. The Steam shortcut (what is on disk)"
python3 - <<'PY'
import glob, os, struct, sys

def read_map(data, pos):
    out = {}
    while True:
        if pos >= len(data):
            raise ValueError("truncated")
        kind = data[pos]; pos += 1
        if kind == 0x08:
            return out, pos
        end = data.find(b"\0", pos)
        key = data[pos:end].decode("utf-8", "replace"); pos = end + 1
        if kind == 0x01:
            end = data.find(b"\0", pos)
            out[key] = data[pos:end].decode("utf-8", "replace"); pos = end + 1
        elif kind == 0x02:
            out[key] = struct.unpack_from("<I", data, pos)[0]; pos += 4
        elif kind == 0x00:
            out[key], pos = read_map(data, pos)
        else:
            raise ValueError(f"type {kind:#x}")
    return out, pos

for path in glob.glob(os.path.expanduser("~/.steam/steam/userdata/*/config/shortcuts.vdf")) + \
            glob.glob(os.path.expanduser("~/.local/share/Steam/userdata/*/config/shortcuts.vdf")):
    print(f"  {path}")
    try:
        with open(path, "rb") as fh:
            parsed, _ = read_map(fh.read(), 0)
        for index, entry in (parsed.get("shortcuts") or {}).items():
            if not isinstance(entry, dict):
                continue
            exe = str(entry.get("exe", ""))
            if "pokebonk" not in exe.lower():
                continue
            print(f"    [{index}] appname={entry.get('appname')!r}")
            print(f"        exe={exe!r}")
            print(f"        icon={entry.get('icon')!r}")
            print(f"        AllowOverlay={entry.get('AllowOverlay')}")
            print(f"        LaunchOptions={entry.get('LaunchOptions')!r}")
            print(f"        appid={entry.get('appid')}")
    except Exception as error:
        print(f"    ! {error}")
PY

line "3. The capsule artwork"
for d in "$STEAM_ROOT"/app/*/; do
  if [ -f "$d/library_hero.jpg" ]; then
    echo "  $d"
    ls -la "$d" | sed 's/^/    /'
  fi
done

line "4. Is the Steam client running?"
if pgrep -x steam >/dev/null 2>&1 || pgrep -x steamwebhelper >/dev/null 2>&1; then
  echo "  YES — the client is running."
  echo "  It keeps the shortcut list IN MEMORY and only reads shortcuts.vdf at startup."
  echo "  A shortcut edited on disk is therefore IGNORED until the client restarts."
else
  echo "  no — the client is not running"
fi

line "5. Launch through Steam's own wrapper (this is where the overlay is injected)"
APPUID="$(grep -a -oE 'AppId=[0-9]+' "$STEAM_ROOT/logs/console_log.txt" 2>/dev/null | tail -1 | cut -d= -f2)"
WRAPPER="$STEAM_ROOT/ubuntu12_32/steam-launch-wrapper"
echo "  last appid seen: ${APPUID:-unknown}"
if [ -x "$WRAPPER" ] && [ -x "$LAUNCHER" ]; then
  echo "  running: $WRAPPER -- /home/deck/.../pokebonk-deck-launch.sh"
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
  export DISPLAY="${DISPLAY:-:0}"
  timeout 45 "$WRAPPER" --oom-score-adjust 900 -- \
    "$STEAM_ROOT/ubuntu12_32/reaper" SteamLaunch "AppId=${APPUID:-0}" -- \
    "$LAUNCHER" 2>&1 | grep -vE 'Fontconfig|dbus' | head -40
  echo "  (exit: $?)"
else
  echo "  ! the Steam launch wrapper is not available"
fi

line "6. Kernel log — crashes in the last hour"
if command -v dmesg >/dev/null; then
  dmesg 2>/dev/null | grep -aiE 'segfault|trap|general protection|pokebonk|gameoverlay|gamescope' | tail -15 || echo "  (nothing — needs root to read)"
else
  echo "  dmesg not available"
fi

line "7. The Steam client's own log"
grep -aiE "pokebonk|AppId=$APPUID" "$STEAM_ROOT/logs/console_log.txt" 2>/dev/null | tail -12

line "8. Summary"
echo "  Copy everything above back to the agent."

REPORT_URL="${POKEBONK_REPORT_URL:-http://192.168.4.220:8100/report}"
if command -v curl >/dev/null && [ -n "$REPORT_URL" ]; then
  sleep 0.3
  if curl -fsS --max-time 10 -X POST --data-binary @"$REPORT_FILE" "$REPORT_URL" >/dev/null 2>&1; then
    echo "  report sent to $REPORT_URL"
  else
    echo "  (could not reach $REPORT_URL — copy this output instead)"
  fi
fi
