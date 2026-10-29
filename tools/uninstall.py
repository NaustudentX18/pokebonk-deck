#!/usr/bin/env python3
"""Remove EVERYTHING to do with PokéBonk Deck.

After this runs the machine is exactly as it was before the client was ever
installed, so a fresh install can be tested end to end.

It removes:

  * the installed app, its wrapper, its artwork and its logs
  * the client's state and cache
  * the launcher entry and the icon
  * any AppImage you copied in by hand (Downloads, Desktop, home)
  * the Steam shortcut, the per-title localconfig block, the per-title
    Steam Input layout and the capsule artwork
  * the temporary files the client leaves behind

It leaves everything else alone: your other library entries, your other
localconfig settings, your other Steam Input layouts.

    python3 uninstall.py             # do it
    python3 uninstall.py --dry-run   # show the plan and stop
"""

from __future__ import annotations

import argparse
import glob
import os
import pathlib
import re
import shutil
import struct
import sys
import time

# --------------------------------------------------------------------------- #
# The binary KeyValues1 reader/writer is vendored in here on purpose: this
# script has to work as a single downloaded file, with nothing else beside it.
# --------------------------------------------------------------------------- #

KV_MAP = 0x00
KV_STRING = 0x01
KV_INT32 = 0x02
KV_END = 0x08


class BinVdfError(Exception):
    pass


def read_bin_vdf(data: bytes):
    pos = 0

    def read_cstring() -> str:
        nonlocal pos
        end = data.find(b"\0", pos)
        if end < 0:
            raise BinVdfError("unterminated string")
        out = data[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return out

    def read_value(kind: int):
        nonlocal pos
        if kind == KV_STRING:
            return read_cstring()
        if kind == KV_INT32:
            if pos + 4 > len(data):
                raise BinVdfError("truncated int32")
            # Unsigned: shortcut appids live in [0x80000000, 0xFFFFFFFF].
            value = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            return value
        if kind == KV_MAP:
            return read_map()
        if kind in (0x06, 0x07):
            pos += 8
            return 0
        raise BinVdfError(f"unknown type byte 0x{kind:02x}")

    def read_map() -> dict:
        nonlocal pos
        out = {}
        while True:
            if pos >= len(data):
                raise BinVdfError("unexpected end of data")
            kind = data[pos]
            pos += 1
            if kind == KV_END:
                return out
            key = read_cstring()
            out[key] = read_value(kind)

    root = read_map()
    if pos != len(data):
        raise BinVdfError(f"{len(data) - pos} trailing bytes")
    return root


def write_bin_vdf(root: dict) -> bytes:
    out = bytearray()

    def write_cstring(text: str) -> None:
        out.extend(text.encode("utf-8"))
        out.append(0)

    def write_entry(key: str, value) -> None:
        if isinstance(value, str):
            out.append(KV_STRING)
            write_cstring(key)
            write_cstring(value)
        elif isinstance(value, bool):
            out.append(KV_INT32)
            write_cstring(key)
            out.extend(struct.pack("<I", 1 if value else 0))
        elif isinstance(value, int):
            out.append(KV_INT32)
            write_cstring(key)
            out.extend(struct.pack("<I", value & 0xFFFFFFFF))
        elif isinstance(value, dict):
            out.append(KV_MAP)
            write_cstring(key)
            write_map(value)
        else:
            raise BinVdfError(f"cannot serialise {type(value)}")

    def write_map(mapping: dict) -> None:
        for key, value in mapping.items():
            write_entry(key, value)
        out.append(KV_END)

    shortcuts = root.get("shortcuts", {})
    if not isinstance(shortcuts, dict):
        raise BinVdfError("the root map has no 'shortcuts' section")

    out.append(KV_MAP)
    write_cstring("shortcuts")
    for key, value in shortcuts.items():
        write_entry(key, value)
    out.append(KV_END)
    out.append(KV_END)
    return bytes(out)


# --------------------------------------------------------------------------- #
# What counts as ours
# --------------------------------------------------------------------------- #

MARKERS = ("pokebonk-deck", "pokebonk deck", "pokebonk_deck", "pokebonkdeck")

HOME = pathlib.Path.home()
INSTALL_DIR = HOME / ".local/share/pokebonk-deck"
# The app's userData directory is named after the PRODUCT name, which is
# "PokéBonk Deck" — not after the package name. Both are removed, and so is
# the Electron cache beside it.
STATE_DIRS = [
    HOME / ".config/pokebonk-deck",
    HOME / ".config/PokéBonk Deck",
]
CACHE_DIRS = [
    HOME / ".cache/pokebonk-deck",
    HOME / ".cache/PokéBonk Deck",
]
DESKTOP_FILE = HOME / ".local/share/applications/gg.pokebonk.deck.desktop"
ICON_DIRS = [
    HOME / ".local/share/icons/hicolor/512x512/apps",
    HOME / ".local/share/icons/hicolor/256x256/apps",
    HOME / ".local/share/icons/hicolor/128x128/apps",
    HOME / ".local/share/icons/hicolor/64x64/apps",
    HOME / ".local/share/icons/hicolor/scalable/apps",
]
STEAM_ROOTS = [
    HOME / ".local/share/Steam",
    HOME / ".steam/steam",
    HOME / ".steam/root",
    HOME / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
]
# Where a person might have dropped the AppImage they downloaded.
MANUAL_COPY_DIRS = [HOME / "Downloads", HOME / "Desktop", HOME]

ARTWORK_NAMES = {
    "library_hero.jpg", "library_capsule.jpg", "capsule.jpg", "capsulev5.jpg",
    "header.jpg", "logo.png", "icon.jpg", "icon.png", "purchased.jpg",
}


def ours(text: str) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in MARKERS)


class Report:
    def __init__(self, dry: bool):
        self.dry = dry
        self.lines: list[str] = []

    def remove(self, what: str, path) -> None:
        path = pathlib.Path(path)
        if not path.exists() and not path.is_symlink():
            return
        verb = "would remove" if self.dry else "removing"
        self.lines.append(f"  {verb} {what}: {path}")
        if self.dry:
            return
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError as error:
            self.lines.append(f"  ! could not remove {path}: {error}")


# --------------------------------------------------------------------------- #
# 1. Stop anything that is running
# --------------------------------------------------------------------------- #

def stop_running_client(report: Report) -> None:
    killed = []
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / "comm").read_text().strip()
            cmdline = (proc / "cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        if comm in ("pokebonk-deck",) or ".mount_pokebonk" in cmdline:
            killed.append(proc.name)
    if not killed:
        return
    report.lines.append(f"  stopping the running client (pid {', '.join(killed)})")
    if report.dry:
        return
    for pid in killed:
        try:
            os.kill(int(pid), 15)
        except OSError:
            pass
    time.sleep(1)


def steam_client_running() -> bool:
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            comm = (proc / "comm").read_text().strip()
        except OSError:
            continue
        if comm in ("steam", "steamwebhelper"):
            return True
    return False


# --------------------------------------------------------------------------- #
# 2. Steam
# --------------------------------------------------------------------------- #

def userdata_dirs(root: pathlib.Path):
    base = root / "userdata"
    if not base.is_dir():
        return []
    return [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()]


def our_appids(root: pathlib.Path) -> dict:
    """profile directory -> the appids of our shortcuts."""
    found = {}
    for profile in userdata_dirs(root):
        shortcuts = profile / "config" / "shortcuts.vdf"
        if not shortcuts.is_file():
            continue
        try:
            entries = read_bin_vdf(shortcuts.read_bytes()).get("shortcuts", {})
        except (OSError, BinVdfError):
            continue
        appids = set()
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            if ours(entry.get("exe", "")) or ours(entry.get("appname", "")):
                if isinstance(entry.get("appid"), int):
                    appids.add(str(entry["appid"] & 0xFFFFFFFF))
        if appids:
            found[profile] = appids
    return found


def clean_shortcuts(root: pathlib.Path, report: Report) -> None:
    for profile in userdata_dirs(root):
        shortcuts = profile / "config" / "shortcuts.vdf"
        if not shortcuts.is_file():
            continue
        try:
            parsed = read_bin_vdf(shortcuts.read_bytes())
        except (OSError, BinVdfError) as error:
            report.lines.append(f"  ! {shortcuts}: {error}")
            continue

        entries = parsed.get("shortcuts", {})
        if not isinstance(entries, dict):
            continue

        keep, dropped = {}, []
        for index, entry in entries.items():
            if isinstance(entry, dict) and (ours(entry.get("exe", "")) or ours(entry.get("appname", ""))):
                dropped.append(entry.get("appname") or entry.get("exe"))
                continue
            keep[index] = entry

        if not dropped:
            continue
        for name in dropped:
            report.lines.append(f"  {'would remove' if report.dry else 'removing'} Steam shortcut: {name}")
        if report.dry:
            continue
        parsed["shortcuts"] = keep
        try:
            shutil.copy2(shortcuts, shortcuts.with_suffix(".vdf.bak"))
            shortcuts.write_bytes(write_bin_vdf(parsed))
        except OSError as error:
            report.lines.append(f"  ! could not write {shortcuts}: {error}")


def clean_localconfig(root: pathlib.Path, report: Report, appids: dict) -> None:
    for profile in userdata_dirs(root):
        localconfig = profile / "config" / "localconfig.vdf"
        if not localconfig.is_file():
            continue
        text = localconfig.read_text(encoding="utf-8", errors="surrogateescape")
        changed = False
        for appid in appids.get(profile, set()):
            pattern = re.compile(
                r'\n[ \t]*"' + re.escape(appid) + r'"[ \t]*\n[ \t]*\{[^{}]*\}', re.S)
            new_text, count = pattern.subn("", text)
            if count:
                text = new_text
                changed = True
                report.lines.append(
                    f"  {'would remove' if report.dry else 'removing'} localconfig block for appid {appid}")
        if changed and not report.dry:
            try:
                shutil.copy2(localconfig, localconfig.with_suffix(".vdf.bak"))
                localconfig.write_text(text, encoding="utf-8", errors="surrogateescape")
            except OSError as error:
                report.lines.append(f"  ! could not write {localconfig}: {error}")


def clean_input_config(root: pathlib.Path, report: Report) -> None:
    for profile in userdata_dirs(root):
        base = (root / "steamapps/common/Steam Controller Configs" / profile.name / "config")
        configset = base / "configset_controller_neptune.vdf"
        if not configset.is_file():
            continue
        text = configset.read_text(encoding="utf-8", errors="replace")
        changed = False
        for marker in MARKERS:
            key = "".join(c for c in marker.lower() if c not in '/\\?%*:|"<>.')
            pattern = re.compile(r'\t"' + re.escape(key) + r'"\n\t\{[^{}]*\}\n', re.S)
            text, count = pattern.subn("", text)
            if count:
                changed = True
                report.lines.append(
                    f"  {'would remove' if report.dry else 'removing'} Steam Input layout for {key!r}")
        if changed and not report.dry:
            try:
                shutil.copy2(configset, configset.with_suffix(".vdf.bak"))
                configset.write_text(text, encoding="utf-8")
            except OSError as error:
                report.lines.append(f"  ! could not write {configset}: {error}")


def clean_artwork(root: pathlib.Path, report: Report) -> None:
    app_root = root / "app"
    if not app_root.is_dir():
        return
    for app_dir in app_root.iterdir():
        if not app_dir.is_dir():
            continue
        names = {f.name for f in app_dir.iterdir()}
        if not (names & ARTWORK_NAMES):
            continue
        report.lines.append(
            f"  {'would remove' if report.dry else 'removing'} capsule artwork: {app_dir}")
        if report.dry:
            continue
        for name in names & ARTWORK_NAMES:
            try:
                (app_dir / name).unlink()
            except OSError:
                pass
        try:
            app_dir.rmdir()
        except OSError:
            pass


def clean_steam_backups(root: pathlib.Path, report: Report) -> None:
    """Remove the .bak files we wrote, but only if they still mention us."""
    for profile in userdata_dirs(root):
        for name in ("shortcuts.vdf.bak", "localconfig.vdf.bak"):
            backup = profile / "config" / name
            if not backup.is_file():
                continue
            try:
                blob = backup.read_bytes()
            except OSError:
                continue
            if not any(marker.encode() in blob.lower() for marker in MARKERS):
                continue
            report.remove(f"backup {name}", backup)


# --------------------------------------------------------------------------- #
# 3. The app's own files
# --------------------------------------------------------------------------- #

def clean_app_files(report: Report) -> None:
    report.remove("the installed app", INSTALL_DIR)
    for state_dir in STATE_DIRS:
        report.remove("the client's state", state_dir)
    for cache_dir in CACHE_DIRS:
        report.remove("the client's cache", cache_dir)
    report.remove("the launcher entry", DESKTOP_FILE)
    for icon_dir in ICON_DIRS:
        if not icon_dir.is_dir():
            continue
        for icon in icon_dir.iterdir():
            if ours(icon.name):
                report.remove("the icon", icon)


def clean_manual_copies(report: Report) -> None:
    """Any AppImage the user copied in by hand."""
    seen = set()
    for directory in MANUAL_COPY_DIRS:
        if not directory.is_dir():
            continue
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry in seen or not entry.is_file():
                continue
            name = entry.name.lower()
            if name.endswith(".appimage") and ours(name):
                seen.add(entry)
                report.remove("a copy you downloaded", entry)


def clean_temp(report: Report) -> None:
    for pattern in ("/tmp/.mount_pokebonk*", "/tmp/pokebonk-deck*",
                    "/tmp/pokebonk_deck*"):
        for path in glob.glob(pattern):
            report.remove("a temporary file", path)


# --------------------------------------------------------------------------- #
# 4. Verify
# --------------------------------------------------------------------------- #

def verify(report: Report) -> list[str]:
    """What is still there? Anything listed here is a leftover."""
    leftovers = []
    for path in [INSTALL_DIR, *STATE_DIRS, *CACHE_DIRS, DESKTOP_FILE]:
        if path.exists():
            leftovers.append(str(path))
    for root in STEAM_ROOTS:
        if not root.is_dir():
            continue
        for profile in userdata_dirs(root):
            shortcuts = profile / "config" / "shortcuts.vdf"
            if shortcuts.is_file():
                try:
                    entries = read_bin_vdf(shortcuts.read_bytes()).get("shortcuts", {})
                except (OSError, BinVdfError):
                    entries = {}
                for entry in entries.values():
                    if isinstance(entry, dict) and (ours(entry.get("exe", ""))
                                                    or ours(entry.get("appname", ""))):
                        leftovers.append(f"Steam shortcut {entry.get('appname')!r}")
        art = root / "app"
        if art.is_dir():
            for app_dir in art.iterdir():
                if app_dir.is_dir() and ({f.name for f in app_dir.iterdir()} & ARTWORK_NAMES):
                    leftovers.append(f"capsule artwork {app_dir}")
    return leftovers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be removed and change nothing")
    args = parser.parse_args()

    report = Report(args.dry_run)
    print("PokéBonk Deck — complete uninstall")
    if args.dry_run:
        print("(dry run — nothing is changed)")

    if steam_client_running():
        print("  ! the Steam client is running — it rewrites shortcuts.vdf on exit,")
        print("    so quit Steam first, then run this.")

    stop_running_client(report)

    for root in STEAM_ROOTS:
        if not root.is_dir():
            continue
        appids = our_appids(root)
        clean_shortcuts(root, report)
        clean_localconfig(root, report, appids)
        clean_input_config(root, report)
        clean_artwork(root, report)
        clean_steam_backups(root, report)

    clean_app_files(report)
    clean_manual_copies(report)
    clean_temp(report)

    for line in report.lines:
        print(line)

    leftovers = verify(report)
    print()
    if args.dry_run:
        print(f"Dry run complete. {len(report.lines)} item(s) would be removed.")
        return 0

    if leftovers:
        print("Still present (the Steam client may have put these back — quit Steam and re-run):")
        for item in leftovers:
            print(f"  - {item}")
    else:
        print("Everything is gone. The machine is back to a fresh-install state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
