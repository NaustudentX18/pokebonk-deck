# Installing PokéBonk Deck

The client ships as a single AppImage. SteamOS 3 already contains every library it needs, and
the Electron sandbox works through unprivileged user namespaces — so there is nothing to
install, no `pacman`, no Flatpak, and no root.

## One command (any x86-64 Linux)

```bash
curl -fsSL https://github.com/NaustudentX18/pokebonk-deck/releases/latest/download/install.sh | bash
```

Downloads the latest AppImage, verifies its sha512 against `latest-linux.yml`, installs it to
`~/.local/share/pokebonk-deck/pokebonk-deck.AppImage`, writes
`~/.local/share/applications/gg.pokebonk.deck.desktop`, installs the launcher icon and adds
the game to your **Steam library** so it appears in Game Mode with the controller set to the
gamepad layout. Re-running it upgrades in place.

The Steam integration:

- creates the shortcut through Steam's own `steam://addnonsteamgame/<path>` handler, so
  Steam assigns the appid and writes `shortcuts.vdf` itself
- points the title at the neptune **gamepad** layout in
  `Steam Controller Configs/<id>/config/configset_controller_neptune.vdf` — without a
  per-title entry Steam falls back to the Desktop Layout, where the trackpads drive the
  mouse instead of the game
- writes `UseSteamControllerConfig`, the launch options and a `1280x800` resolution
  override into `localconfig.vdf`
- writes a launcher wrapper that uses gamemode when it is available and falls back when
  it is not (`gamemoderun` is not on PATH inside the Steam Linux Runtime 3 container)

Nothing it writes is destructive: `localconfig.vdf` is patched surgically, `shortcuts.vdf` is
parsed and rewritten only if it is fully understood, and both are backed up.

## Steam Deck (SteamOS 3)

1. Either run the installer above, or open the
   [releases page](https://github.com/NaustudentX18/pokebonk-deck/releases) on the Deck's
   browser (or copy the file over via microSD, USB or SSH) and download
   `PokebonkDeck-1.0.9-x86_64.AppImage`.
2. In Desktop Mode, open a terminal and make it executable:

   ```bash
   chmod +x ~/Downloads/PokebonkDeck-1.0.9-x86_64.AppImage
   mkdir -p ~/.local/share/pokebonk-deck
   mv ~/Downloads/PokebonkDeck-1.0.9-x86_64.AppImage ~/.local/share/pokebonk-deck/
   ```

3. In Steam, go to **Library → Add a Non-Steam Game → Browse**, and pick the AppImage.
4. Right-click the shortcut → **Properties → General → Launch Options** and set:

   ```
   gamemoderun %command%
   ```

   `gamemode` ships with SteamOS and applies the performance governor, the CPU/GPU boost
   policy and the correct refresh-rate behaviour.

5. Start it from the Library. The game goes fullscreen immediately.

### Why the AppImage belongs on internal storage

The self-updater replaces the AppImage in place with a `rename()` over the running file. A
rename cannot cross filesystems, so an AppImage on a FAT32 microSD card cannot be updated
in place. Internal storage is one filesystem and updates fine.

### Controller layout in Steam

Steam Input offers two action sets: **Desktop** (the Deck's buttons act as mouse and
keyboard) and **Gamepad**. The game reads the Gamepad API, so use the Gamepad layout:

- In-game: hold **Menu** to toggle action sets.
- In Steam's per-game controller settings, make sure the layout is a gamepad, not "Desktop
  Layout".

If the controller does not appear at all, see [troubleshooting.md](troubleshooting.md).

## Desktop Linux

```bash
chmod +x PokebonkDeck-1.0.9-x86_64.AppImage
./PokebonkDeck-1.0.9-x86_64.AppImage
```

Any current x86-64 Linux with a working Mesa stack works. The AppImage bundles Electron and
Chromium; only the handful of system libraries Chromium needs come from the host, and every
major distro ships them.

## Running from source

```bash
git clone https://github.com/NaustudentX18/pokebonk-deck.git
cd pokebonk-deck
npm ci
npm start
```

The self-updater is inert when the app is not launched as an AppImage (`APPIMAGE` is unset),
which is expected in a source checkout.

## Verifying the download

```bash
sha256sum PokebonkDeck-1.0.9-x86_64.AppImage
```

Compare against the checksum published in the release notes.
