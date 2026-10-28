#!/usr/bin/env python3
"""End-to-end test: run the Steam integration against a fake Steam profile.

Builds a realistic ~/.local/share/Steam tree (binary shortcuts.vdf with an
existing game, a text localconfig.vdf with an 'apps' section) and checks that
the tool adds the shortcut, preserves the existing one, and writes the
per-title settings without disturbing anything else.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import steam_integration as si  # noqa: E402

spec = importlib.util.spec_from_file_location("t", HERE / "test-steam-integration.py")
builder = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(builder)
except SystemExit:
    pass

EXISTING = builder._build_reference_shortcuts_vdf([
    builder.shortcut_entry(
        exe='"/usr/bin/kodi"',
        app_name="Kodi",
        appid=2443196458,
        start_dir="/usr/bin",
        icon="",
        launch_options="",
    )
])

LOCALCONFIG = '''"UserLocalConfigStore"
{
	"friends"
	{
		"Person"		"76561198000000001"
	}
	"Software"
	{
		"Valve"
		{
			"Steam"
			{
				"apps"
				{
					"70"
					{
						"LastPlayed"		"1700000000"
					}
				}
				"OtherKey"
				{
					"Keep"		"me"
				}
			}
		}
	}
}
'''


def build_fake_steam(root: Path) -> Path:
    profile = root / "userdata" / "123456789"
    (profile / "config").mkdir(parents=True)
    (profile / "config" / "shortcuts.vdf").write_bytes(EXISTING)
    (profile / "config" / "localconfig.vdf").write_text(LOCALCONFIG, encoding="utf-8")
    return profile


def main() -> int:
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        steam_root = home / ".local/share/Steam"
        profile = build_fake_steam(steam_root)

        # Point the module at the fake tree.
        si.STEAM_ROOTS = (steam_root,)
        si.Path.home = staticmethod(lambda: home)

        exe = str(home / ".local/share/pokebonk-deck/pokebonk-deck.AppImage")
        Path(exe).parent.mkdir(parents=True, exist_ok=True)
        Path(exe).write_text("#!/bin/sh\n")
        os.chmod(exe, 0o755)

        launcher = home / ".local/share/pokebonk-deck/launch.sh"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text("#!/bin/sh\nexec \"$@\"\n")
        os.chmod(launcher, 0o755)

        # A fake Valve template so the Steam Input step has something to point at.
        templates = steam_root / "controller_base/templates"
        templates.mkdir(parents=True)
        (templates / "controller_neptune_gamepad+mouse.vdf").write_text('"x" {}\n')

        rc = si.main([
            "--exe", exe,
            "--name", "PokéBonk Deck",
            "--launcher", str(launcher),
            "--launch-options", "",
            "--resolution", "1280x800",
        ])
        if rc != 0:
            failures.append(f"tool returned {rc}")

        shortcuts = profile / "config" / "shortcuts.vdf"
        parsed = si.read_bin_vdf(shortcuts.read_bytes())
        entries = parsed["shortcuts"]

        # The pre-existing game must survive untouched.
        if "0" not in entries:
            failures.append("the existing shortcut was lost")
        elif entries["0"].get("appname") != "Kodi":
            failures.append("the existing shortcut was modified")

        # The new shortcut must be there.
        found = [e for e in entries.values()
                 if isinstance(e, dict) and e.get("appname") == "PokéBonk Deck"]
        if not found:
            failures.append("the new shortcut was not added")
        else:
            entry = found[0]
            # The path is stored unquoted: Steam's own URL handler takes a
            # plain path, and passing a pre-quoted one double-quotes it.
            if entry.get("exe") != str(launcher):
                failures.append(f"exe is not the launcher: {entry.get('exe')!r}")
            if entry.get("AllowOverlay") != 0:
                failures.append(f"the Steam overlay must be off: {entry.get('AllowOverlay')!r}")
            if entry["LaunchOptions"] != "":
                failures.append(f"LaunchOptions should be empty: {entry['LaunchOptions']!r}")
            if not isinstance(entry["appid"], int) or entry["appid"] < 0x80000000:
                failures.append(f"appid not in the NSG range: {entry['appid']!r}")

            # The per-title settings must be in localconfig.vdf.
            text = (profile / "config" / "localconfig.vdf").read_text(encoding="utf-8")
            appid = str(entry["appid"])
            if f'"{appid}"' not in text:
                failures.append("no per-app block in localconfig.vdf")
            if '"LaunchOptions"\t\t""' not in text:
                failures.append("LaunchOptions not written")
            if '"UseSteamControllerConfig"\t\t"1"' not in text:
                failures.append("Steam Input not enabled")
            if '"ResolutionOverride"\t\t"1280x800"' not in text:
                failures.append("resolution override not written")
            if '"Person"\t\t"76561198000000001"' not in text:
                failures.append("unrelated config was damaged")
            if text.count("{") != text.count("}"):
                failures.append("unbalanced braces in localconfig.vdf")

        # A second run must correct an entry the Steam client created itself
        # (overlay on, wrong title) rather than adding another one.
        si.update_entry(shortcuts, str(launcher), "PokéBonk Deck", "", allow_overlay=False)
        updated = si.read_bin_vdf(shortcuts.read_bytes())["shortcuts"]
        ours = [e for e in updated.values()
                if isinstance(e, dict) and e.get("exe") == str(launcher)]
        if len(ours) != 1:
            failures.append(f"expected one entry, found {len(ours)}")
        elif ours[0].get("AllowOverlay") != 0:
            failures.append("the overlay was not turned off on the existing entry")
        elif ours[0].get("appname") != "PokéBonk Deck":
            failures.append(f"title not corrected: {ours[0].get('appname')!r}")

        # The Steam Input configset must point the title at a gamepad layout.
        configset = (steam_root / "steamapps/common/Steam Controller Configs"
                     / profile.name / "config/configset_controller_neptune.vdf")
        if not configset.is_file():
            failures.append("no Steam Input configset was written")
        else:
            body = configset.read_text(encoding="utf-8")
            if si.transform_title("PokéBonk Deck") not in body:
                failures.append(f"configset has no title key: {body!r}")
            if "controller_neptune_gamepad+mouse.vdf" not in body:
                failures.append("configset does not select the gamepad template")

        # A second run must not duplicate the shortcut.
        before = len(entries)
        si.main([
            "--exe", exe,
            "--name", "PokéBonk Deck",
            "--launcher", str(launcher),
            "--launch-options", "",
            "--resolution", "1280x800",
        ])
        after = len(si.read_bin_vdf(shortcuts.read_bytes())["shortcuts"])
        if after != before:
            failures.append(f"re-running duplicated the shortcut ({before} -> {after})")

    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("OK: shortcut added, existing library preserved, settings applied, re-run is idempotent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
