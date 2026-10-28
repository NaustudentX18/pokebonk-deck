# Deck hardware verification

**Status: pending — the Deck has not been verified yet.**

This file is the record of what was actually measured on real Steam Deck
hardware. It is deliberately empty of claims: nothing goes in here that was not
read off the device.

## What is verified so far

| Check | Where | Result |
|---|---|---|
| Electron 45 loads the live game and boots it | this machine (Intel UHD 630, Mesa) | ✅ WebGL2, `ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL ES 3.2)`, build `mvr5gbc0` |
| `localStorage` persists on the `https://pokebonk.com` origin | this machine | ✅ `pb.device` survives a restart |
| The AppImage is FUSE3-free with a conditional sandbox | this machine | ✅ `scripts/verify-build.sh` |
| The installer works from the release asset | this machine, clean `$HOME` | ✅ checksum verified, desktop entry, icon, Steam shortcut, per-title settings, Steam Input configset |
| **Controller in the game (Game Mode)** | **the Deck** | ⏳ pending |
| **Fullscreen at 1280×800 on the Deck's panel** | **the Deck** | ⏳ pending |
| **The game updates itself** | **the Deck** | ⏳ pending |
| **Saves survive a restart on the Deck** | **the Deck** | ⏳ pending |

## How to run the verification

On the Deck, in **Desktop Mode**, with the client installed:

```bash
curl -fsSL https://github.com/NaustudentX18/pokebonk-deck/releases/latest/download/deck-verify.sh | bash
```

That single command:

1. prints the OS, kernel, user-namespace state, the GPU stack, the **joydev**
   nodes Chromium needs, `/run/udev` visibility, the Steam Input action-set
   reminder, and the AppImage's library prerequisites;
2. runs the client's own `--selftest`, which loads the live game and reports
   the origin, the upstream build, the WebGL2 renderer, whether the renderer
   is a software rasteriser, the connected gamepads and the preload bridge;
3. posts the whole report to the collector, so the results arrive without
   anyone copying and pasting.

If the collector is unreachable the report is still printed and saved to
`/tmp/pokebonk-deck-report.txt` on the Deck.

## The manual version

If the script cannot run, these are the commands that matter, in order:

```bash
# 1. The controller must appear as a joydev node, with ID_INPUT_JOYSTICK=1.
ls -l /dev/input/js* /dev/input/event*
udevadm info -q property -n /dev/input/js0 | grep -E 'ID_INPUT_JOYSTICK|NAME|PRODUCT'

# 2. Chromium needs libudev; inside the Steam Linux Runtime this is the
#    classic cause of "no controller".
ls /run/udev

# 3. The client itself, on the Deck's GPU.
~/.local/share/pokebonk-deck/pokebonk-deck.AppImage --selftest
```

The self-test prints one line:

```
SELFTEST_JSON {"ok":true,"checks":{...}}
```

with `renderer` (must be the AMD GPU, not `llvmpipe`/`swiftshader`),
`softwareRenderer` (must be `false`), `origin` (must be
`https://pokebonk.com`) and `gamepads`.

## Reading the result

| Symptom | Meaning | Fix |
|---|---|---|
| `gamepads: []` but the pad is plugged in | Chromium's user-gesture gate | press a button; the pad appears |
| `gamepads: []` in Game Mode | Steam Input is on the **Desktop** layout | the installer points the title at the gamepad layout; confirm in Steam → Settings → Controller |
| `renderer` contains `llvmpipe`/`swiftshader` | the GPU is not being used | check `/dev/dri` is passed through |
| `/run/udev` missing | launched inside a container without udev | check the Steam Linux Runtime's `/dev/input` passthrough |
| `webgl2: false` | the game cannot start | the Deck's Mesa is broken — verify `/dev/dri/renderD128` |

## The four things that must be true

1. **The pad works in the game.** `gamepads` lists a real pad (not a Steam
   virtual one), and the in-game glyphs are the Xbox set.
2. **It is fullscreen at 1280×800.** The game fills the panel with no browser
   chrome.
3. **Saves persist.** Play, quit, relaunch — the guest session and the league
   progress are still there.
4. **The game updates itself.** When the upstream build id changes, the client
   offers the reload and lands on the new build.

## Notes to fill in after the run

- Deck model / SteamOS version:
- Date and time of the run:
- Output of `deck-verify.sh`:
- Anything that did not work, and what was changed:
