#!/usr/bin/env python3
"""Test the launcher wrapper that install.sh writes.

The wrapper has to do exactly two things:
  - remove gameoverlayrenderer.so from LD_PRELOAD, leaving every other
    library in place
  - run the app, through gamemode when it exists and directly when it does not

Run: python3 tools/test-launcher.py
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent


def extract_wrapper(install_sh: str) -> str:
    """Pull the wrapper source out of install.sh's heredoc."""
    match = re.search(
        r"cat > \"\$LAUNCHER\" <<EOF\n(.*?)\nEOF\n", install_sh, re.S)
    if not match:
        raise SystemExit("could not find the launcher heredoc in install.sh")
    body = match.group(1)
    # Undo the escaping install.sh applies so the result is the real script.
    body = body.replace('\\$', '$').replace('\\`', '`').replace('\\\\', '\\')
    return body


def preload_of(stdout: str) -> str:
    """The APP-PRELOAD line the test app prints."""
    for line in stdout.splitlines():
        if line.startswith("APP-PRELOAD="):
            return line.strip()
    return stdout.strip()


def main() -> int:
    install_sh = (REPO / "install.sh").read_text()
    wrapper = extract_wrapper(install_sh)
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        app = work / "app.sh"
        app.write_text('#!/bin/sh\necho "APP-PRELOAD=[${LD_PRELOAD:-}]"\n')
        app.chmod(0o755)

        # Real libraries, so the loader does not print "cannot be preloaded".
        lib_a = "/usr/lib/libglib-2.0.so.0"
        lib_b = "/usr/lib/libz.so.1"
        overlay = "/home/deck/.local/share/Steam/gameoverlayrenderer.so"

        launcher = work / "launch.sh"
        launcher.write_text(wrapper.replace('"$APPIMAGE"', f'"{app}"'))
        launcher.chmod(0o755)

        # 1. The overlay library is removed, everything else stays.
        env = dict(os.environ)
        env["LD_PRELOAD"] = f"{lib_a}:{overlay}:{lib_b}"
        out = subprocess.run([str(launcher)], env=env, capture_output=True, text=True, timeout=20)
        preload = preload_of(out.stdout)
        expected = f"APP-PRELOAD=[{lib_a}:{lib_b}]"
        if preload != expected:
            failures.append(f"preload not cleaned as expected:\n    got      {preload}\n    expected {expected}")

        # 2. With no overlay in the chain, the chain is left alone.
        env["LD_PRELOAD"] = lib_a
        out = subprocess.run([str(launcher)], env=env, capture_output=True, text=True, timeout=20)
        if preload_of(out.stdout) != f"APP-PRELOAD=[{lib_a}]":
            failures.append(f"a clean preload chain was modified: {preload_of(out.stdout)!r}")

        # 3. With no preload at all the app still runs.
        env.pop("LD_PRELOAD", None)
        out = subprocess.run([str(launcher)], env=env, capture_output=True, text=True, timeout=20)
        if preload_of(out.stdout) != "APP-PRELOAD=[]":
            failures.append(f"the app did not run without LD_PRELOAD: {preload_of(out.stdout)!r}")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK: the launcher strips the overlay and leaves the rest of the chain alone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
