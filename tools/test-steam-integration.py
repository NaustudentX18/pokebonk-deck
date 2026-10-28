#!/usr/bin/env python3
"""Tests for the Steam integration: binary VDF round-trip and localconfig patching.

Run: python3 tools/test-steam-integration.py
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from steam_integration import (  # noqa: E402
    BinVdfError,
    _find_block,
    patch_localconfig,
    read_bin_vdf,
    shortcut_entry,
    write_bin_vdf,
)


def _kv_str(key: str, value: str) -> bytes:
    """A string entry: type byte, NUL-terminated key, NUL-terminated value."""
    return (b"\x01" + key.encode("utf-8") + b"\x00"
            + value.encode("utf-8") + b"\x00")


def _kv_int(key: str, value: int) -> bytes:
    """An int32 entry: type byte, NUL-terminated key, 4 raw little-endian bytes."""
    # Unsigned: appids are in [0x80000000, 0xFFFFFFFF].
    return b"\x02" + key.encode("utf-8") + b"\x00" + struct.pack("<I", value & 0xFFFFFFFF)


def _build_reference_shortcuts_vdf(entries: list[dict]) -> bytes:
    """Build a shortcuts.vdf the way Valve's writer would."""
    out = bytearray()
    out += b"\x00" + b"shortcuts\x00"
    for index, entry in enumerate(entries):
        out += b"\x00" + str(index).encode() + b"\x00"
        out += _kv_int("appid", entry["appid"])
        out += _kv_str("appname", entry["appname"])
        out += _kv_str("exe", entry["exe"])
        out += _kv_str("StartDir", entry["StartDir"])
        out += _kv_str("icon", entry["icon"])
        out += _kv_str("ShortcutPath", entry["ShortcutPath"])
        out += _kv_str("LaunchOptions", entry["LaunchOptions"])
        out += _kv_int("IsHidden", entry["IsHidden"])
        out += _kv_int("AllowDesktopConfig", entry["AllowDesktopConfig"])
        out += _kv_int("AllowOverlay", entry["AllowOverlay"])
        out += _kv_int("OpenVR", entry["OpenVR"])
        out += _kv_int("Devkit", entry["Devkit"])
        out += _kv_str("DevkitGameID", entry["DevkitGameID"])
        out += _kv_int("LastPlayTime", entry["LastPlayTime"])
        out += _kv_str("FlatpakAppID", entry["FlatpakAppID"])
        out += b"\x00" + b"tags\x00"
        # Tag entries are plain string key/value pairs, not nested maps:
        #   \x01 "0" \x00 "favorite" \x00
        for tag_index, tag in enumerate(entry.get("tags", {}).values()):
            out += _kv_str(str(tag_index), tag)
        out += b"\x08"  # end of the tags map
        out += b"\x08"  # end of the entry map
    out += b"\x08"  # end of the "shortcuts" map
    out += b"\x08"  # end of the file
    return bytes(out)


class BinaryVdfTest(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        entry = shortcut_entry(
            exe='"/home/deck/Applications/pokebonk-deck.AppImage"',
            app_name="PokéBonk Deck",
            appid=2443196458,
            start_dir="/home/deck/Applications",
            icon="",
            launch_options="gamemoderun %command%",
        )
        original = _build_reference_shortcuts_vdf([entry])

        parsed = read_bin_vdf(original)
        self.assertIn("shortcuts", parsed)
        self.assertEqual(parsed["shortcuts"]["0"]["appname"], "PokéBonk Deck")
        self.assertEqual(parsed["shortcuts"]["0"]["appid"], 2443196458)
        self.assertEqual(parsed["shortcuts"]["0"]["tags"]["0"], "favorite")

        rewritten = write_bin_vdf(parsed)
        self.assertEqual(rewritten, original, "binary VDF round-trip must be byte-identical")

    def test_non_ascii_survives_the_round_trip(self):
        entry = shortcut_entry(
            exe='"/home/déck/Applications/pokebonk-deck.AppImage"',
            app_name="PokéBonk Deck",
            appid=1234567890,
            start_dir="/home/déck/Applications",
            icon="",
            launch_options="gamemoderun %command%",
        )
        original = _build_reference_shortcuts_vdf([entry])
        parsed = read_bin_vdf(original)
        self.assertEqual(parsed["shortcuts"]["0"]["exe"], entry["exe"])
        self.assertEqual(write_bin_vdf(parsed), original)

    def test_garbage_is_rejected_rather_than_rewritten(self):
        with self.assertRaises(BinVdfError):
            read_bin_vdf(b"\x00shortcuts\x00\x01Exe\x00oops")

    def test_trailing_bytes_are_rejected(self):
        entry = shortcut_entry(
            exe="/x", app_name="n", appid=1, start_dir="/", icon="", launch_options="")
        data = _build_reference_shortcuts_vdf([entry]) + b"junk"
        with self.assertRaises(BinVdfError):
            read_bin_vdf(data)


class LocalconfigPatchTest(unittest.TestCase):
    SAMPLE = '''"UserLocalConfigStore"
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

    def test_finds_the_apps_block(self):
        found = _find_block(self.SAMPLE, "apps")
        self.assertIsNotNone(found)
        start, end = found
        self.assertIn('"70"', self.SAMPLE[start:end])
        self.assertNotIn('"OtherKey"', self.SAMPLE[start:end])

    def test_inserts_the_app_block_without_touching_anything_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "localconfig.vdf"
            path.write_text(self.SAMPLE, encoding="utf-8")

            ok = patch_localconfig(path, "999888777", {
                "LaunchOptions": "gamemoderun %command%",
                "UseSteamControllerConfig": "1",
            })
            self.assertTrue(ok)

            text = path.read_text(encoding="utf-8")
            self.assertIn('"999888777"', text)
            self.assertIn('"LaunchOptions"\t\t"gamemoderun %command%"', text)
            self.assertIn('"UseSteamControllerConfig"\t\t"1"', text)
            # everything else survives
            self.assertIn('"Person"\t\t"76561198000000001"', text)
            self.assertIn('"OtherKey"', text)
            self.assertIn('"LastPlayed"\t\t"1700000000"', text)
            # braces stay balanced
            self.assertEqual(text.count("{"), text.count("}"))

    def test_replaces_an_existing_block_instead_of_duplicating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "localconfig.vdf"
            path.write_text(self.SAMPLE, encoding="utf-8")

            patch_localconfig(path, "70", {"LaunchOptions": "gamemoderun %command%"})
            patch_localconfig(path, "70", {"LaunchOptions": "gamemoderun %command%"})

            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count('"70"'), 1)
            self.assertEqual(text.count("gamemoderun"), 1)
            self.assertEqual(text.count("{"), text.count("}"))

    def test_escapes_quotes_and_backslashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "localconfig.vdf"
            path.write_text(self.SAMPLE, encoding="utf-8")
            patch_localconfig(path, "555", {"LaunchOptions": 'a "b" \\c'})
            text = path.read_text(encoding="utf-8")
            self.assertIn('\\"b\\"', text)
            self.assertIn("\\\\c", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
