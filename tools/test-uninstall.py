#!/usr/bin/env python3
"""Test the uninstaller against a synthetic Steam profile.

Builds a profile with our client AND someone else's game in it, runs the
uninstaller, and checks that ours is gone and theirs is untouched.
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

spec = importlib.util.spec_from_file_location("t", HERE / "test-steam-integration.py")
builder = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(builder)
except SystemExit:
    pass

import steam_integration as si  # noqa: E402


def build_profile(root: pathlib.Path) -> pathlib.Path:
    profile = root / "userdata" / "123456789"
    (profile / "config").mkdir(parents=True)
    (profile / "config" / "shortcuts.vdf").write_bytes(
        builder._build_reference_shortcuts_vdf([
            builder.shortcut_entry(exe='"/usr/bin/kodi"', app_name="Kodi",
                                   appid=2443196458, start_dir="/usr/bin",
                                   icon="", launch_options=""),
            builder.shortcut_entry(
                exe="/home/deck/.local/share/pokebonk-deck/pokebonk-deck-launch.sh",
                app_name="PokéBonk Deck", appid=4112265388,
                start_dir="/home/deck/.local/share/pokebonk-deck", icon="",
                launch_options=""),
        ]))
    (profile / "config" / "localconfig.vdf").write_text(
        '"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n'
        '\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
        '\t\t\t\t\t"70"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1700000000"\n'
        '\t\t\t\t\t}\n'
        '\t\t\t\t\t"4112265388"\n\t\t\t\t\t{\n'
        '\t\t\t\t\t\t"LaunchOptions"\t\t""\n'
        '\t\t\t\t\t\t"UseSteamControllerConfig"\t\t"1"\n'
        '\t\t\t\t\t}\n'
        '\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')

    configset = (root / "steamapps/common/Steam Controller Configs/123456789/config")
    configset.mkdir(parents=True)
    (configset / "configset_controller_neptune.vdf").write_text(
        '"controller_config"\n{\n'
        '\t"pokebonk deck"\n\t{\n\t\t"template"\t\t"controller_neptune_gamepad+mouse.vdf"\n\t}\n'
        '\t"something else"\n\t{\n\t\t"template"\t\t"controller_neptune_xinput.vdf"\n\t}\n'
        '}\n')

    art = root / "app" / "4112265388"
    art.mkdir(parents=True)
    for name in ("library_hero.jpg", "capsule.jpg", "header.jpg", "logo.png"):
        (art / name).write_bytes(b"x")
    return profile


def main() -> int:
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp) / "home"
        steam_root = home / ".local/share/Steam"
        profile = build_profile(steam_root)

        # Fake the install too.
        install = home / ".local/share/pokebonk-deck"
        install.mkdir(parents=True)
        (install / "pokebonk-deck.AppImage").write_text("x")
        (install / "artwork").mkdir()
        (home / ".local/share/applications").mkdir(parents=True)
        (home / ".local/share/applications/gg.pokebonk.deck.desktop").write_text("x")
        (home / ".config/pokebonk-deck").mkdir(parents=True)
        (home / ".config/pokebonk-deck/deck-state.json").write_text("{}")

        # Point the uninstaller at the fake home.
        import uninstall
        uninstall.HOME = home
        uninstall.INSTALL_DIR = install
        uninstall.DESKTOP_FILE = home / ".local/share/applications/gg.pokebonk.deck.desktop"
        uninstall.ICON_FILE = home / ".local/share/icons/hicolor/512x512/apps/pokebonk-deck.png"
        uninstall.STATE_DIR = home / ".config/pokebonk-deck"
        uninstall.STEAM_ROOTS = (steam_root,)

        rc = uninstall.main()
        if rc != 0:
            failures.append(f"uninstaller returned {rc}")

        # The install is gone.
        for path in (install, home / ".config/pokebonk-deck",
                     home / ".local/share/applications/gg.pokebonk.deck.desktop"):
            if path.exists():
                failures.append(f"still present: {path}")

        # Our shortcut is gone, Kodi is not.
        entries = si.read_bin_vdf((profile / "config/shortcuts.vdf").read_bytes())["shortcuts"]
        names = [e.get("appname") for e in entries.values() if isinstance(e, dict)]
        if "PokéBonk Deck" in names:
            failures.append(f"our shortcut survived: {names}")
        if "Kodi" not in names:
            failures.append(f"someone else's shortcut was removed: {names}")

        # Our localconfig block is gone, the other one is not.
        text = (profile / "config/localconfig.vdf").read_text()
        if "4112265388" in text:
            failures.append("our localconfig block survived")
        if "1700000000" not in text:
            failures.append("someone else's localconfig block was removed")

        # Our Steam Input entry is gone, the other one is not.
        configset = (steam_root / "steamapps/common/Steam Controller Configs/123456789"
                     "/config/configset_controller_neptune.vdf").read_text()
        if "pokebonk" in configset:
            failures.append("our Steam Input entry survived")
        if "something else" not in configset:
            failures.append("someone else's Steam Input entry was removed")

        # The artwork is gone.
        if (steam_root / "app/4112265388").exists():
            failures.append("the artwork folder survived")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK: our client is gone, everything else is untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
