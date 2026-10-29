#!/usr/bin/env python3
"""Test the complete uninstaller against a synthetic machine.

Builds a machine with the client installed (app, state, cache, desktop entry,
icon, a hand-downloaded AppImage, the Steam shortcut, the localconfig block,
the Steam Input layout and the capsule artwork) plus someone else's game, then
checks that ours is gone and theirs is untouched.

Run: python3 tools/test-uninstall.py
"""

from __future__ import annotations

import importlib.util
import pathlib
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
import uninstall  # noqa: E402


def build_machine(home: pathlib.Path) -> pathlib.Path:
    steam_root = home / ".local/share/Steam"
    profile = steam_root / "userdata" / "123456789"
    (profile / "config").mkdir(parents=True)

    # Someone else's game and ours, in the same library.
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

    configset = (steam_root / "steamapps/common/Steam Controller Configs/123456789/config")
    configset.mkdir(parents=True)
    (configset / "configset_controller_neptune.vdf").write_text(
        '"controller_config"\n{\n'
        '\t"pokebonk deck"\n\t{\n\t\t"template"\t\t"controller_neptune_gamepad+mouse.vdf"\n\t}\n'
        '\t"something else"\n\t{\n\t\t"template"\t\t"controller_neptune_xinput.vdf"\n\t}\n'
        '}\n')

    art = steam_root / "app" / "4112265388"
    art.mkdir(parents=True)
    for name in ("library_hero.jpg", "capsule.jpg", "header.jpg", "logo.png"):
        (art / name).write_bytes(b"x")

    # The install itself.
    install = home / ".local/share/pokebonk-deck"
    (install / "artwork").mkdir(parents=True)
    (install / "pokebonk-deck.AppImage").write_text("x")
    (install / "pokebonk-deck-launch.sh").write_text("x")
    (install / "launch.log").write_text("x")

    (home / ".config/pokebonk-deck").mkdir(parents=True)
    (home / ".config/pokebonk-deck/deck-state.json").write_text("{}")
    # The real one: Electron names the userData directory after productName.
    (home / ".config/PokéBonk Deck").mkdir(parents=True)
    (home / ".config/PokéBonk Deck/deck-state.json").write_text("{}")
    (home / ".cache/pokebonk-deck").mkdir(parents=True)
    (home / ".cache/pokebonk-deck/Cache").write_text("x")

    apps = home / ".local/share/applications"
    apps.mkdir(parents=True)
    (apps / "gg.pokebonk.deck.desktop").write_text("x")

    icons = home / ".local/share/icons/hicolor/512x512/apps"
    icons.mkdir(parents=True)
    (icons / "pokebonk-deck.png").write_text("x")
    (icons / "something-else.png").write_text("x")

    # A copy the user downloaded by hand.
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    (downloads / "PokebonkDeck-1.2.1-x86_64.AppImage").write_text("x")
    (downloads / "holiday-photo.jpg").write_text("x")

    return steam_root


def main() -> int:
    failures = []

    with tempfile.TemporaryDirectory() as tmp:
        home = pathlib.Path(tmp) / "home"
        steam_root = build_machine(home)

        uninstall.HOME = home
        uninstall.INSTALL_DIR = home / ".local/share/pokebonk-deck"
        uninstall.STATE_DIRS = [home / ".config/pokebonk-deck",
                               home / ".config/PokéBonk Deck"]
        uninstall.CACHE_DIRS = [home / ".cache/pokebonk-deck",
                                home / ".cache/PokéBonk Deck"]
        uninstall.DESKTOP_FILE = home / ".local/share/applications/gg.pokebonk.deck.desktop"
        uninstall.ICON_DIRS = [home / ".local/share/icons/hicolor/512x512/apps"]
        uninstall.STEAM_ROOTS = (steam_root,)
        uninstall.MANUAL_COPY_DIRS = [home / "Downloads", home / "Desktop", home]

        # A dry run changes nothing.
        rc = uninstall.main.__wrapped__() if hasattr(uninstall.main, "__wrapped__") else None
        sys.argv = ["uninstall.py", "--dry-run"]
        if uninstall.main() != 0:
            failures.append("the dry run returned non-zero")
        if not (home / ".local/share/pokebonk-deck").exists():
            failures.append("the dry run removed something")

        # The real thing.
        sys.argv = ["uninstall.py"]
        if uninstall.main() != 0:
            failures.append("the uninstall returned non-zero")

        # Gone: the app, its state and cache, the desktop entry, the icon,
        # the hand-downloaded copy.
        for path in (
            home / ".local/share/pokebonk-deck",
            home / ".config/pokebonk-deck",
            home / ".config/PokéBonk Deck",
            home / ".cache/pokebonk-deck",
            home / ".local/share/applications/gg.pokebonk.deck.desktop",
            home / ".local/share/icons/hicolor/512x512/apps/pokebonk-deck.png",
            home / "Downloads/PokebonkDeck-1.2.1-x86_64.AppImage",
        ):
            if path.exists():
                failures.append(f"still present: {path}")

        # Untouched: everything that belongs to the user.
        for path in (
            home / ".local/share/icons/hicolor/512x512/apps/something-else.png",
            home / "Downloads/holiday-photo.jpg",
        ):
            if not path.exists():
                failures.append(f"someone else's file was removed: {path}")

        # The Steam library: ours gone, theirs intact.
        profile = steam_root / "userdata" / "123456789"
        entries = si.read_bin_vdf((profile / "config/shortcuts.vdf").read_bytes())["shortcuts"]
        names = [e.get("appname") for e in entries.values() if isinstance(e, dict)]
        if "PokéBonk Deck" in names:
            failures.append(f"our shortcut survived: {names}")
        if "Kodi" not in names:
            failures.append(f"someone else's shortcut was removed: {names}")

        text = (profile / "config/localconfig.vdf").read_text()
        if "4112265388" in text:
            failures.append("our localconfig block survived")
        if "1700000000" not in text:
            failures.append("someone else's localconfig block was removed")

        configset = (steam_root / "steamapps/common/Steam Controller Configs/123456789"
                     "/config/configset_controller_neptune.vdf").read_text()
        if "pokebonk" in configset:
            failures.append("our Steam Input entry survived")
        if "something else" not in configset:
            failures.append("someone else's Steam Input entry was removed")

        if (steam_root / "app/4112265388").exists():
            failures.append("the artwork folder survived")

        # And the verifier agrees that nothing is left.
        leftovers = uninstall.verify(uninstall.Report(dry=False))
        if leftovers:
            failures.append(f"the verifier still sees: {leftovers}")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("OK: everything of ours is gone, everything else is untouched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
