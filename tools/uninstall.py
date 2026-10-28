#!/usr/bin/env python3
"""Remove every trace of the PokéBonk Deck client.

Safe to run at any time: it only ever removes what the installer created, and
it leaves the rest of the Steam library alone.

    python3 uninstall.py            # remove it
    python3 uninstall.py --dry-run  # show what would go
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import sys

# The binary KeyValues1 reader/writer is vendored in here on purpose: this
# script has to work as a single downloaded file, with nothing else beside it.

# Type bytes in Valve's binary KeyValues1 format.
KV_MAP = 0x00
KV_STRING = 0x01
KV_INT32 = 0x02
KV_END = 0x08


class BinVdfError(Exception):
    pass


def read_bin_vdf(data: bytes):
    """Parse a binary KeyValues1 blob into nested dicts/lists/values."""
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
            # Unsigned: shortcut appids live in [0x80000000, 0xFFFFFFFF] and
            # do not fit a signed 32-bit int.
            value = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            return value
        if kind == KV_MAP:
            return read_map()
        if kind in (0x06, 0x07):  # uint64 / int64
            if pos + 8 > len(data):
                raise BinVdfError("truncated int64")
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
        # Trailing bytes mean we did not understand the file. Refuse to write.
        raise BinVdfError(f"{len(data) - pos} trailing bytes")
    return root


def write_bin_vdf(root: dict) -> bytes:
    """Serialise back to Valve's binary KeyValues1, byte-for-byte reversible."""
    out = bytearray()

    def write_cstring(text: str) -> None:
        out.extend(text.encode("utf-8"))
        out.append(0)

    def write_map(mapping: dict) -> None:
        for key, value in mapping.items():
            write_entry(key, value)
        out.append(KV_END)

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

    shortcuts = root.get("shortcuts", {})
    if not isinstance(shortcuts, dict):
        raise BinVdfError("the root map has no 'shortcuts' section")

    # File shape: <00> "shortcuts" <entry...> <08> <08>
    # The leading 0x00 is the root map's type byte; the two end markers close
    # the "shortcuts" map and then the file.
    out.append(KV_MAP)
    write_cstring("shortcuts")
    for key, value in shortcuts.items():
        write_entry(key, value)
    out.append(KV_END)  # end of the "shortcuts" map
    out.append(KV_END)  # end of the file
    return bytes(out)



HOME = pathlib.Path.home()
INSTALL_DIR = HOME / ".local/share/pokebonk-deck"
DESKTOP_FILE = HOME / ".local/share/applications/gg.pokebonk.deck.desktop"
ICON_FILE = HOME / ".local/share/icons/hicolor/512x512/apps/pokebonk-deck.png"
STATE_DIR = HOME / ".config/pokebonk-deck"
STEAM_ROOTS = (
    HOME / ".local/share/Steam",
    HOME / ".steam/steam",
    HOME / ".steam/root",
)

# Anything under these names belongs to us.
OUR_MARKERS = ("pokebonk-deck", "pokebonk deck")


def ours(text: str) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in OUR_MARKERS)


def userdata_dirs(root: pathlib.Path):
    base = root / "userdata"
    if not base.is_dir():
        return []
    return [d for d in base.iterdir() if d.is_dir() and d.name.isdigit()]


def remove_shortcuts(root: pathlib.Path, dry: bool) -> list[str]:
    """Drop our entries from the binary shortcuts.vdf, keep every other one."""
    removed = []
    for profile in userdata_dirs(root):
        shortcuts = profile / "config" / "shortcuts.vdf"
        if not shortcuts.is_file():
            continue
        try:
            parsed = read_bin_vdf(shortcuts.read_bytes())
        except (OSError, BinVdfError) as error:
            print(f"  ! {shortcuts}: {error}")
            continue

        entries = parsed.get("shortcuts", {})
        if not isinstance(entries, dict):
            continue

        keep = {}
        for index, entry in entries.items():
            if isinstance(entry, dict) and (
                ours(entry.get("exe", "")) or ours(entry.get("appname", ""))
            ):
                removed.append(f"shortcut {entry.get('appname') or entry.get('exe')!r} "
                               f"(appid {entry.get('appid')})")
                continue
            keep[index] = entry

        if len(keep) == len(entries):
            continue
        parsed["shortcuts"] = keep
        if dry:
            continue
        shutil.copy2(shortcuts, shortcuts.with_suffix(".vdf.bak"))
        try:
            shortcuts.write_bytes(write_bin_vdf(parsed))
        except OSError as error:
            print(f"  ! could not write {shortcuts}: {error}")
    return removed


def our_appids(root: pathlib.Path) -> dict:
    """Map each profile directory to the appids of our shortcuts.

    This has to run BEFORE the shortcuts are removed — once they are gone
    there is nothing left to tell us which appid was ours.
    """
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


def remove_localconfig(root: pathlib.Path, dry: bool, appids=None) -> list[str]:
    """Remove the per-app blocks we added to localconfig.vdf."""
    removed = []
    for profile in userdata_dirs(root):
        localconfig = profile / "config" / "localconfig.vdf"
        if not localconfig.is_file():
            continue
        text = localconfig.read_text(encoding="utf-8", errors="surrogateescape")

        # Our blocks are the ones whose appid we recorded in the shortcuts file.
        if appids is None:
            appids = our_appids(root)
        ours_for_profile = appids.get(profile, set())

        changed = False
        for appid in ours_for_profile:
            pattern = re.compile(
                r'\n[ \t]*"' + re.escape(appid) + r'"[ \t]*\n[ \t]*\{[^{}]*\}',
                re.S)
            new_text, count = pattern.subn("", text)
            if count:
                text = new_text
                changed = True
                removed.append(f"localconfig block for appid {appid}")

        if changed and not dry:
            shutil.copy2(localconfig, localconfig.with_suffix(".vdf.bak"))
            localconfig.write_text(text, encoding="utf-8", errors="surrogateescape")
    return removed


def remove_input_config(root: pathlib.Path, dry: bool) -> list[str]:
    """Remove our entry from the per-title Steam Input configset."""
    removed = []
    for profile in userdata_dirs(root):
        base = root / "steamapps/common/Steam Controller Configs" / profile.name / "config"
        configset = base / "configset_controller_neptune.vdf"
        if not configset.is_file():
            continue
        text = configset.read_text(encoding="utf-8", errors="replace")
        changed = False
        for marker in OUR_MARKERS:
            key = "".join(c for c in marker.lower()
                           if c not in '/\\?%*:|"<>.')
            pattern = re.compile(r'\t"' + re.escape(key) + r'"\n\t\{[^{}]*\}\n', re.S)
            text, count = pattern.subn("", text)
            if count:
                changed = True
                removed.append(f"Steam Input layout for {key!r}")
        if changed and not dry:
            shutil.copy2(configset, configset.with_suffix(".vdf.bak"))
            configset.write_text(text, encoding="utf-8")
    return removed


def remove_artwork(root: pathlib.Path, dry: bool) -> list[str]:
    """Remove the capsule art we installed into <steam>/app/<appid>/."""
    removed = []
    app_root = root / "app"
    if not app_root.is_dir():
        return removed
    for app_dir in app_root.iterdir():
        if not app_dir.is_dir():
            continue
        names = {f.name for f in app_dir.iterdir()}
        if names & {"library_hero.jpg", "library_capsule.jpg", "capsulev5.jpg"}:
            removed.append(f"capsule artwork in app/{app_dir.name}/")
            if not dry:
                for name in names:
                    if name in {"library_hero.jpg", "library_capsule.jpg",
                                "capsule.jpg", "capsulev5.jpg", "header.jpg",
                                "logo.png", "icon.jpg", "purchased.jpg"}:
                        try:
                            (app_dir / name).unlink()
                        except OSError:
                            pass
                try:
                    app_dir.rmdir()
                except OSError:
                    pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("PokéBonk Deck uninstaller")
    if args.dry_run:
        print("(dry run — nothing is changed)")

    try:
        from steam_integration import steam_client_running
        if steam_client_running():
            print("  ! the Steam client is running — it rewrites shortcuts.vdf on exit,")
            print("    so it may put the shortcut back. Quit Steam first, then run this.")
    except ImportError:
        pass

    # 1. Files the installer created.
    for path in (INSTALL_DIR, STATE_DIR):
        if path.exists():
            print(f"  {'would remove' if args.dry_run else 'removing'} {path}")
            if not args.dry_run:
                shutil.rmtree(path, ignore_errors=True)
    for path in (DESKTOP_FILE, ICON_FILE):
        if path.exists():
            print(f"  {'would remove' if args.dry_run else 'removing'} {path}")
            if not args.dry_run:
                try:
                    path.unlink()
                except OSError:
                    pass

    # 2. Steam.
    for root in STEAM_ROOTS:
        if not root.is_dir():
            continue
        # Collect our appids before the shortcuts go away.
        appids = our_appids(root)
        for what, result in (
            ("shortcut", remove_shortcuts(root, args.dry_run)),
            ("localconfig", remove_localconfig(root, args.dry_run, appids)),
            ("steam input", remove_input_config(root, args.dry_run)),
            ("artwork", remove_artwork(root, args.dry_run)),
        ):
            for line in result:
                print(f"  {'would remove' if args.dry_run else 'removing'} {what}: {line}")

    if args.dry_run:
        print("\nDry run complete. Re-run without --dry-run to remove.")
    else:
        print("\nRemoved. The Deck is back to a fresh-install state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
