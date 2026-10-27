# Troubleshooting

## The controller does not work in the game

**Press a button first.** Chromium hides gamepads until the user has interacted with one.
At launch the game will see nothing; press any button on the Deck's controls and the pad
appears. The shell's `F8` shortcut prints exactly what the client sees.

If a pad still does not appear:

1. **Check the Steam Input layout.** Steam Input has two action sets: Desktop (buttons act
   as mouse/keyboard) and Gamepad. The game reads the Gamepad API, so use the Gamepad set.
   Hold **Menu** in-game to toggle, or change it in Steam's per-game controller settings.
2. **Run the native Linux build.** A Proton/Windows build is a different code path
   (Electron ≥ 27 lost the Gamepad API on Windows under Steam Input). This project ships
   native Linux only.
3. **Check the joydev node exists** on the Deck:

   ```bash
   ls -l /dev/input/js* /dev/input/event*
   udevadm info -q property -n /dev/input/js0 | grep -E 'ID_INPUT_JOYSTICK|NAME'
   ```

   You want a js node for `Microsoft X-Box 360 pad 0` (Steam Input's virtual pad) and/or
   `Steam Deck`, with `ID_INPUT_JOYSTICK=1`. Chromium on Linux reads buttons and axes from
   the **joydev** node (`/dev/input/js*`), not from the raw evdev node.

4. **Still stuck?** The client's `F8` output plus the commands above are enough to diagnose
   it. Open an issue with both.

## "Your browser is not using your graphics card"

The game detects software rasterisers (`swiftshader`, `llvmpipe`, `softpipe`) and warns that
it is running without hardware acceleration. On a Deck this means the GPU is not being used.

- Make sure the app is not launched with `--disable-gpu`.
- Confirm SteamOS's Mesa is intact (`glxinfo -B` should report the AMD GPU).
- Under a container (Flatpak, the Steam Linux Runtime), check that the GPU device is actually
  passed through.

## My save or progress is gone

Saves live in `localStorage` on the `https://pokebonk.com` origin, inside the client's
persistent Chromium profile. A different profile means a different (empty) store.

- Never launch the unpacked directory and the AppImage interchangeably — use the AppImage.
- Do not clear the app's data in Steam.
- Signing in to a PokéBonk account moves progress to the server, where it is independent of
  the local profile.

## A new game build did not load

The client polls `version.json` on an interval and reloads when the build id changes. Force
it with `F5`, or restart the app.

If the game itself keeps showing its own "new version" banner, that is upstream behaviour —
the game's own check compares the running bundle's compiled-in build id against `version.json`
and prompts a reload after a jittered delay.

## The self-updater says it is inactive

The in-app updater only works when the app is running **as an AppImage** (`APPIMAGE` is set in
the environment). Running from source, an unpacked directory, or a `deb` install means the
updater is inert by design — the file cannot be replaced in place.

## The AppImage will not run

```
dlopen(): error loading libfuse.so.2
AppImages require FUSE to run.
```

This build uses the **static, FUSE3-free** runtime, so it should never need FUSE. If you see
this error you are running an older build. Download the current release.

## The window does not go fullscreen

The client requests kiosk mode at launch. If a desktop environment overrides it, `F11` toggles
fullscreen manually. On Wayland, some window managers intercept fullscreen requests; the
`gamemoderun %command%` launch option avoids most of that by running inside gamescope.

## Reset everything

```bash
rm -rf ~/.config/pokebonk-deck ~/.local/share/pokebonk-deck
```

That removes the persistent profile — including the local guest session. Cloud saves tied to
a PokéBonk account survive.
