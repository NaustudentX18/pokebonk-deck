#!/usr/bin/env bash
# Assert the built AppImage is safe for SteamOS 3:
#   1. it uses the STATIC, FUSE3-free runtime (no libfuse dependency)
#   2. it does not unconditionally disable the Chromium sandbox
#   3. the update manifest the in-app updater polls exists
set -euo pipefail
cd "$(dirname "$0")/.."

APPIMAGE="$(ls -1 dist/*.AppImage 2>/dev/null | head -1 || true)"
if [ -z "$APPIMAGE" ]; then
  echo "FAIL: no AppImage in dist/ — run 'npm run build' first"; exit 1
fi

WORK="${TMPDIR:-/tmp}/pb-verify"
rm -rf "$WORK" && mkdir -p "$WORK"
( cd "$WORK" && "$OLDPWD/$APPIMAGE" --appimage-extract >/dev/null )
APPRUN="$WORK/squashfs-root/AppRun"

# 1. Static runtime: the legacy FUSE2 runtime links libfuse; the static one does not.
if ldd "$APPRUN" 2>/dev/null | grep -qi fuse; then
  echo "FAIL: AppRun links libfuse — the legacy FUSE2 runtime was used."
  echo "      Set \"toolsets\": { \"appimage\": \"1.0.3\" } in the build config."
  exit 1
fi

# 2. Sandbox: the static runtime decides at runtime whether to pass --no-sandbox.
#    It must contain the unshare heuristic; an unconditional injection would
#    disable the Chromium sandbox on every launch.
if ! grep -q 'unshare -Ur true' "$APPRUN"; then
  echo "FAIL: AppRun has no user-namespace probe — --no-sandbox may be forced."
  exit 1
fi
if grep -qE '^NO_SANDBOX=\(--no-sandbox\)' "$APPRUN"; then
  # Column-0 assignment: the sandbox would always be off. The static runtime
  # assigns it *inside* the conditional branch, so it is indented.
  echo "FAIL: AppRun assigns --no-sandbox unconditionally."
  exit 1
fi

# Report what the probe decides on THIS host (the Deck has unprivileged userns).
if unshare -Ur true 2>/dev/null; then
  SANDBOX_STATE="user namespaces available -> sandbox stays ON"
else
  SANDBOX_STATE="user namespaces unavailable -> --no-sandbox will be passed"
fi

# 3. The update manifest the in-app updater polls.
if [ ! -f dist/latest-linux.yml ]; then
  echo "FAIL: dist/latest-linux.yml missing — the updater has nothing to poll."
  echo "      Build with a publish provider configured (see package.json > build.publish)."
  exit 1
fi

echo "PASS: static FUSE3-free runtime, conditional sandbox handling, latest-linux.yml present"
echo "      $SANDBOX_STATE"
echo "      $(du -h "$APPIMAGE" | cut -f1)  $APPIMAGE"
