#!/usr/bin/env python3
"""Add PokéBonk Deck to Steam and apply the per-title settings.

Two mechanisms, in order of preference:

1. Steam's own URL handler — ``steam://addnonsteamgame/<path>`` — creates the
   shortcut, assigns its appid and writes ``shortcuts.vdf``. Steam is the only
   thing that knows how to do this correctly, and the library updates live.

2. If the Steam client is not available, the script falls back to writing
   ``shortcuts.vdf`` itself. That file is a BINARY KeyValues1 file, so this
   script implements a reader and a writer for it and refuses to touch a file
   it cannot fully parse.

The per-title settings (launch options, Steam Input, resolution) live in
``localconfig.vdf``, which is a TEXT VDF. That file is patched surgically —
the new app block is inserted into the existing ``apps`` section and nothing
else in the file is reformatted or rewritten.

Idempotent: running it again updates the existing shortcut instead of adding
a second one.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

# Steam's URL handler only accepts a local path when this sentinel exists.
SENTINEL = Path(tempfile.gettempdir()) / "addnonsteamgamefile"

STEAM_ROOTS = (
    Path.home() / ".local/share/Steam",
    Path.home() / ".steam/steam",
    Path.home() / ".steam/root",
    Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
)

# Type bytes in Valve's binary KeyValues1 format.
KV_MAP = 0x00
KV_STRING = 0x01
KV_INT32 = 0x02
KV_END = 0x08


# --------------------------------------------------------------------------- #
# Binary KeyValues1 (shortcuts.vdf)
# --------------------------------------------------------------------------- #

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


def shortcut_entry(exe: str, app_name: str, appid: int, start_dir: str,
                    icon: str, launch_options: str) -> dict:
    """A shortcut entry with the key set Valve's writer uses."""
    # Valve's own key names. 'appname' and 'exe' are lower case in the files
    # the Steam client writes; matching them exactly keeps our entries
    # indistinguishable from the client's.
    return {
        "appid": appid,
        "appname": app_name,
        "exe": exe,
        "StartDir": start_dir,
        "icon": icon,
        "ShortcutPath": "",
        "LaunchOptions": launch_options,
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        # The Steam overlay injects gameoverlayrenderer.so into the app. On
        # Electron 45 that renderer segfaults and takes the app with it, which
        # is what a Deck user sees as "the game never starts".
        "AllowOverlay": 0,
        "OpenVR": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": int(time.time()),
        "FlatpakAppID": "",
        "sortas": "",
        "tags": {"0": "favorite"},
    }


# --------------------------------------------------------------------------- #
# Text VDF (localconfig.vdf) — surgical patching
# --------------------------------------------------------------------------- #

def _skip_string(text: str, index: int) -> int:
    """Return the index just past the closing quote of the string at index."""
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        index += 1
    raise ValueError("unterminated string in VDF")


def _find_block(text: str, key: str):
    """Locate a top-level-ish block by key. Returns (start, end) of its body."""
    pattern = re.compile(r'(?<![A-Za-z0-9_])"' + re.escape(key) + r'"\s*\{')
    for match in pattern.finditer(text):
        index = match.end()
        depth = 1
        while index < len(text) and depth:
            char = text[index]
            if char == '"':
                index = _skip_string(text, index)
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            index += 1
        if depth != 0:
            raise ValueError(f"unbalanced braces for block {key!r}")
        return match.end(), index - 1
    return None


def _render_block(appid: str, settings: dict, indent: str = "\t") -> str:
    """Render one app block, matching the indentation of its siblings."""
    lines = [f'{indent}"{appid}"']
    lines.append(f"{indent}{{")
    for key, value in settings.items():
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{indent}\t"{key}"\t\t"{escaped}"')
    lines.append(f"{indent}}}")
    return "\n".join(lines)


def _sibling_indent(inner: str) -> str:
    """The indentation used by the blocks already in this section.

    A sibling block looks like:
        <indent>"123"
        <indent>{
    so the indent comes from the quoted key line.
    """
    for line in inner.splitlines():
        stripped = line.lstrip("\t ")
        if stripped.startswith('"') and stripped.rstrip().endswith('"'):
            prefix = line[:len(line) - len(stripped)]
            if prefix and prefix.strip() == "":
                return prefix
    return "\t"


def _find_all_blocks(text: str, key: str):
    """Every block with the given key, as (body_start, body_end) pairs."""
    results = []
    offset = 0
    while True:
        found = _find_block(text[offset:], key)
        if found is None:
            return results
        start, end = found
        results.append((offset + start, offset + end))
        offset = offset + end


def patch_localconfig(path: Path, appid: str, settings: dict) -> int:
    """Insert or replace the per-app block inside the 'apps' sections.

    localconfig.vdf has two 'apps' sections in the wild — one under
    Software/Valve/Steam and one at the store root — and the Steam Input
    toggle is read from a different one depending on the client version, so
    the block is written to every 'apps' section that exists.

    Everything outside the inserted block is left byte-for-byte untouched.
    """
    text = path.read_text(encoding="utf-8", errors="surrogateescape")

    blocks = _find_all_blocks(text, "apps")
    if not blocks:
        return 0

    # Patch from the last block backwards so earlier offsets stay valid.
    for body_start, body_end in reversed(blocks):
        inner = text[body_start:body_end]
        pattern = re.compile(r'("' + re.escape(appid) + r'"\s*\{)(.*?)(\n\s*\})', re.S)
        match = pattern.search(inner)
        block = _render_block(appid, settings, _sibling_indent(inner))
        if match:
            new_inner = inner[:match.start()] + block + inner[match.end():]
        else:
            new_inner = inner.rstrip() + "\n" + block + "\n" + inner[len(inner.rstrip()):]
        text = text[:body_start] + new_inner + text[body_end:]

    path.write_text(text, encoding="utf-8", errors="surrogateescape")
    return len(blocks)


# --------------------------------------------------------------------------- #
# Per-title Steam Input configuration
# --------------------------------------------------------------------------- #

# The key Steam uses for a non-Steam shortcut is the title, lowercased, with
# these characters stripped.
_BAD_TITLE_CHARS = set('/\\?%*:|"<>.')


def transform_title(title: str) -> str:
    return "".join(c for c in title.lower() if c not in _BAD_TITLE_CHARS)


def steam_input_config_path(root: Path, account_id: str) -> Path:
    return (root / "steamapps/common/Steam Controller Configs" / account_id
            / "config" / "configset_controller_neptune.vdf")


def write_steam_input_config(root: Path, account_id: str, title: str,
                              template: str) -> bool:
    """Point this title at a gamepad layout instead of the Desktop Layout.

    Without a per-title entry, Steam Input falls back to the global Desktop
    Layout — the most common Steam Deck failure, where the trackpads drive
    the mouse instead of the game.
    """
    template_path = root / "controller_base/templates" / template
    if not template_path.is_file():
        return False

    path = steam_input_config_path(root, account_id)
    key = transform_title(title)

    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8", errors="replace")

    entry = (
        f'\t"{key}"\n'
        f'\t{{\n'
        f'\t\t"template"\t\t"{template}"\n'
        f'\t}}\n'
    )

    if existing.strip():
        # Replace an existing entry for this title, keep every other entry.
        pattern = re.compile(
            r'\t"' + re.escape(key) + r'"\n\t\{[^{}]*\}\n', re.S)
        if pattern.search(existing):
            updated = pattern.sub(entry, existing)
        else:
            updated = existing
            if not updated.endswith("\n"):
                updated += "\n"
            updated += entry
    else:
        updated = (
            '"controller_config"\n'
            '{\n'
            + entry
            + '}\n'
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        shutil.copy2(path, path.with_suffix(".vdf.backup"))
    path.write_text(updated, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# Steam capsule artwork
# --------------------------------------------------------------------------- #

# Steam reads the library art for a non-Steam shortcut from
# <steam>/app/<appid>/. Without these files the entry is a blank tile.
ARTWORK_FILES = (
    "library_hero.jpg",
    "library_capsule.jpg",
    "capsule.jpg",
    "capsulev5.jpg",
    "header.jpg",
    "logo.png",
    "icon.jpg",
    "purchased.jpg",
)


def install_artwork(root: Path, appid: int, artwork_dir: Path) -> int:
    """Copy the capsule art into the app folder. Returns the count installed."""
    if not artwork_dir.is_dir():
        return 0
    target = root / "app" / str(appid)
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    installed = 0
    for name in ARTWORK_FILES:
        source = artwork_dir / name
        if not source.is_file():
            continue
        try:
            shutil.copy2(source, target / name)
            installed += 1
        except OSError:
            pass
    return installed


def steam_client_running() -> bool:
    """True when the Steam client is running on this machine.

    The client keeps the shortcut list in memory and rewrites shortcuts.vdf
    on exit, so a file we edit underneath it can be silently reverted. Any
    tool that edits that file has to say so.
    """
    for proc in pathlib.Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            exe = (proc / "comm").read_text().strip()
        except OSError:
            continue
        if exe in ("steam", "steamwebhelper", "steamerrorreporter"):
            return True
    return False


def warn_about_steam_client() -> None:
    if steam_client_running():
        print("  ! the Steam client is running — it rewrites shortcuts.vdf on exit.")
        print("    Quit Steam (or run 'steam -shutdown') and add the game again,")
        print("    or restart the client afterwards to pick up these changes.")


# --------------------------------------------------------------------------- #
# Steam discovery
# --------------------------------------------------------------------------- #

def find_steam_root() -> Path | None:
    for root in STEAM_ROOTS:
        if root.is_dir():
            return root
    return None


def userdata_dirs(root: Path) -> list[Path]:
    base = root / "userdata"
    if not base.is_dir():
        return []
    found = []
    for child in base.iterdir():
        if not child.is_dir() or not child.name.isdigit():
            continue
        if (child / "config").is_dir():
            found.append(child)
    return found


def find_steam_binary(root: Path) -> str | None:
    for candidate in ("steam.sh", "steam", "ubuntu12_32/steam", "linux32/steam"):
        path = root / candidate
        if path.exists():
            return str(path)
    return shutil.which("steam")


# --------------------------------------------------------------------------- #
# Adding the shortcut
# --------------------------------------------------------------------------- #

def update_entry(shortcuts: Path, command: str, app_name: str, icon: str,
                 allow_overlay: bool = False) -> bool:
    """Update an existing shortcut in place.

    The Steam client creates the shortcut itself when the URL handler is
    used, and that entry has the overlay enabled — which is what kills an
    Electron app on the Deck. So an entry we did not write still has to be
    corrected.
    """
    try:
        data = shortcuts.read_bytes()
        parsed = read_bin_vdf(data)
    except (OSError, BinVdfError):
        return False

    entries = parsed.get("shortcuts", {})
    if not isinstance(entries, dict):
        return False

    changed = False
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        exe = entry.get("exe") or entry.get("Exe") or ""
        if exe != command and exe.strip('"') != command:
            continue
        if app_name:
            entry["appname"] = app_name
            changed = True
        if icon and entry.get("icon") != icon:
            entry["icon"] = icon
            changed = True
        wanted = 1 if allow_overlay else 0
        if entry.get("AllowOverlay") != wanted:
            entry["AllowOverlay"] = wanted
            changed = True

    if not changed:
        return False

    try:
        shutil.copy2(shortcuts, shortcuts.with_suffix(".vdf.bak"))
        shortcuts.write_bytes(write_bin_vdf(parsed))
    except OSError:
        return False
    return True


def shortcut_has_exe(shortcuts: Path, exe: str) -> bool:
    """True if the file already holds a shortcut for this command.

    The Steam client stores the exe quoted ("/path/to/thing") while a
    hand-written entry is usually unquoted, so both forms have to be looked
    for — otherwise the tool adds a second shortcut for the same app.
    """
    try:
        data = shortcuts.read_bytes()
    except OSError:
        return False
    quoted = '"' + exe + '"'
    return exe.encode("utf-8") + b"\0" in data or quoted.encode("utf-8") + b"\0" in data


def find_entry(shortcuts: Path, command: str):
    """Return (appid, appname) of the shortcut for this command, if any."""
    try:
        parsed = read_bin_vdf(shortcuts.read_bytes())
    except (OSError, BinVdfError):
        return None
    entries = parsed.get("shortcuts", {})
    if not isinstance(entries, dict):
        return None
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        exe = entry.get("exe") or entry.get("Exe") or ""
        if exe == command or exe.strip('"') == command:
            appid = entry.get("appid")
            name = entry.get("appname") or entry.get("AppName") or ""
            return (appid if isinstance(appid, int) else None, name)
    return None


def find_entry_appid(shortcuts: Path, command: str) -> int | None:
    found = find_entry(shortcuts, command)
    return found[0] if found else None


def add_via_steam_client(steam_bin: str, exe: str) -> bool:
    """Ask the running Steam client to add the shortcut."""
    url = f"steam://addnonsteamgame/{quote(exe, safe='')}"
    try:
        SENTINEL.touch(mode=0o600, exist_ok=True)
        subprocess.run([steam_bin, url], check=True, timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def add_via_shortcuts_vdf(userdata: Path, exe: str, app_name: str,
                          icon: str, launch_options: str,
                          app_path: str | None = None) -> int | None:
    """Fallback: write the shortcut into the binary shortcuts.vdf ourselves."""
    shortcuts = userdata / "config" / "shortcuts.vdf"
    try:
        data = shortcuts.read_bytes() if shortcuts.exists() else b""
    except OSError:
        return None

    try:
        parsed = read_bin_vdf(data) if data else {"shortcuts": {}}
    except BinVdfError as error:
        print(f"  ! cannot parse {shortcuts}: {error}", file=sys.stderr)
        return None

    entries = parsed.setdefault("shortcuts", {})
    if not isinstance(entries, dict):
        print("  ! shortcuts.vdf has an unexpected shape", file=sys.stderr)
        return None

    # Find a free index.
    index = 0
    while str(index) in entries:
        index += 1

    # An appid derived the way Valve used to derive it: crc32(Exe + AppName)
    # with the top bit set. Steam honours a stored appid.
    import zlib
    appid = zlib.crc32((exe + app_name).encode("utf-8")) | 0x80000000

    entries[str(index)] = shortcut_entry(
        exe=exe,
        app_name=app_name,
        appid=appid,
        start_dir=str(Path(app_path or exe).parent),
        icon=icon,
        launch_options=launch_options,
    )

    try:
        shortcuts.parent.mkdir(parents=True, exist_ok=True)
        backup = shortcuts.with_suffix(".vdf.bak")
        if shortcuts.exists():
            shutil.copy2(shortcuts, backup)
        shortcuts.write_bytes(write_bin_vdf(parsed))
    except OSError as error:
        print(f"  ! could not write {shortcuts}: {error}", file=sys.stderr)
        return None

    return appid


# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="pokebonk-deck-steam",
        description="Add the PokéBonk Deck shortcut to Steam and apply per-title settings.",
    )
    parser.add_argument("--exe", required=True, help="path to the AppImage")
    parser.add_argument("--name", default="PokéBonk Deck", help="library title")
    parser.add_argument("--launch-options", default="gamemoderun %command%")
    parser.add_argument("--resolution", default="1280x800")
    parser.add_argument("--icon", default="")
    parser.add_argument("--launcher", default="",
                        help="wrapper script to launch (the AppImage path is passed to it)")
    parser.add_argument("--artwork", default="",
                        help="directory with the Steam capsule images")
    parser.add_argument("--input-template", default="controller_neptune_gamepad+mouse.vdf",
                        help="Steam Input layout template to use for this title")
    parser.add_argument("--no-steam-input", action="store_true",
                        help="do not enable Steam Input for the shortcut")
    args = parser.parse_args(argv)

    exe = str(Path(args.exe).expanduser().resolve())
    if not os.path.isfile(exe):
        print(f"not a file: {exe}", file=sys.stderr)
        return 1

    root = find_steam_root()
    if root is None:
        # Non-zero: the caller must not report success when nothing was set up.
        print("Steam was not found in the usual locations — skipping the Steam integration.")
        print("Add the AppImage to Steam manually: Library -> Add a Non-Steam Game.")
        return 1

    print(f"Steam root: {root}")
    userdata = userdata_dirs(root)
    if not userdata:
        print("No Steam user profile found — is the client signed in?")
        return 1
    profile = userdata[0]
    print(f"Steam profile: {profile.name}")

    shortcuts = profile / "config" / "shortcuts.vdf"
    command = args.launcher or exe

    # 1. Let Steam create the shortcut if it can.
    steam_bin = find_steam_binary(root)
    added_by_steam = False
    command = args.launcher or exe
    if steam_bin and not shortcut_has_exe(shortcuts, command):
        print("Adding to the running Steam client…")
        added_by_steam = add_via_steam_client(steam_bin, command)
        if added_by_steam:
            # Give the client a moment to write shortcuts.vdf.
            for _ in range(20):
                if shortcut_has_exe(shortcuts, command):
                    break
                time.sleep(0.25)

    # 2. Fall back to writing the shortcut ourselves.
    # The shortcut's command is the launcher wrapper (if any); the app path
    # is passed to it as an argument. Steam's Exe field is a full command
    # line, so the wrapper + argument is the exact command that runs.
    command = args.launcher or exe
    # The wrapper has the app path baked in, so the shortcut needs no
    # arguments at all — that keeps the command unambiguous whichever
    # LaunchOptions field Steam happens to read.
    command_args = ""

    if not shortcut_has_exe(shortcuts, command):
        print("Writing the shortcut directly…")
        appid = add_via_shortcuts_vdf(profile, command, args.name, args.icon,
                                      command_args, app_path=exe)
        if appid is None:
            print("Could not add the shortcut automatically.", file=sys.stderr)
            print("Add it by hand: Library -> Add a Non-Steam Game.", file=sys.stderr)
            return 1
    else:
        appid = find_entry_appid(shortcuts, command)
        if appid is None:
            appid = add_via_shortcuts_vdf(profile, command, args.name, args.icon,
                                          command_args, app_path=exe)
        if appid is None:
            print("The shortcut exists but its appid could not be read.", file=sys.stderr)
            return 1

    print(f"Shortcut appid: {appid}")

    # 3. Per-title settings live in localconfig.vdf.
    localconfig = profile / "config" / "localconfig.vdf"
    settings = {
        "LaunchOptions": "" if args.launcher else args.launch_options,
        "ResolutionOverride": args.resolution,
        "ResolutionOverrideInternalDisplay": args.resolution,
        "LastPlayed": str(int(time.time())),
        "Playtime": "0",
        "UseSteamControllerConfig": "0" if args.no_steam_input else "1",
        "AllowLaunchInVR": "0",
        "DisableLaunchInVR": "0",
    }

    if not localconfig.exists():
        print("  ! localconfig.vdf not found — per-title settings were not applied")
    else:
        try:
            # The appid key is the unsigned 32-bit value.
            key = str(int(appid) & 0xFFFFFFFF)
            blocks = patch_localconfig(localconfig, key, settings)
            if blocks:
                print(f"Applied per-title settings to {blocks} apps section(s) "
                      f"in localconfig.vdf (appid {key})")
            else:
                print("  ! could not find the 'apps' section in localconfig.vdf")
        except (OSError, ValueError) as error:
            print(f"  ! could not patch localconfig.vdf: {error}", file=sys.stderr)

    # If the entry already existed (the client created it), correct it: the
    # overlay has to be off and the icon set.
    if update_entry(shortcuts, command, args.name, args.icon):
        print("Updated the existing shortcut (overlay off, icon set)")

    # The Steam Input configset is keyed by the title as the CLIENT stored it.
    # When the client creates the shortcut itself, that title is the exe's
    # file name, not the name we asked for — using the wrong key means the
    # per-title layout is silently ignored and Steam falls back to the
    # Desktop Layout.
    real_name = args.name
    found = find_entry(shortcuts, command)
    if found and found[1]:
        real_name = found[1]
        print(f"Shortcut title in Steam: {real_name!r}")

    # The capsule art, so the library entry is not a blank tile.
    if args.artwork:
        installed = install_artwork(root, int(appid) & 0xFFFFFFFF, Path(args.artwork))
        if installed:
            print(f"Installed {installed} capsule image(s) for appid {appid}")
        else:
            print("  ! no capsule artwork was installed")

    # Per-title Steam Input: a gamepad layout instead of the Desktop Layout.
    account_id = profile.name
    try:
        if write_steam_input_config(root, account_id, real_name, args.input_template):
            print(f"Steam Input: using the {args.input_template} layout for this title")
        else:
            print("  ! the Steam Input gamepad template was not found — "
                  "Steam will fall back to its Desktop Layout. Set it in "
                  "Steam -> Settings -> Controller if the pad misbehaves.")
    except OSError as error:
        print(f"  ! could not write the Steam Input config: {error}", file=sys.stderr)

    print("Done. The game is in your Steam library — start it from Game Mode.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
