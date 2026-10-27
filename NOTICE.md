# NOTICE

## What this project is

PokéBonk Deck is an **unofficial community client** for the browser game at
<https://pokebonk.com>.

## What this project is not

- It is **not** affiliated with, sponsored by, or endorsed by the creator of PokéBonk
  (Charcher), or by Nintendo, The Pokémon Company, Creatures Inc. or GAME FREAK inc.
- It is **not** the game. It contains no game code.
- It is **not** an offline copy, a mirror, or a redistribution of the game.

## Game assets

PokéBonk is an unofficial, free, non-profit fan game. The game's own legal notice states that
it is distributed only as a website and is not sold or listed in app stores.

This project **redistributes no game assets** — no sprites, no models, no textures, no audio, no
music, no fonts, no saves. The client loads the live site at `https://pokebonk.com/` as a
top-level document and adds only a window shell, a menu, and update handling.

Gameplay imagery included in `site/media/` is captured from the publicly available game for
identification and demonstration purposes. It shows the game's own title card and characters;
those are the property of their respective owners.

## Trademarks

"Pokémon" and related names, images and designs are trademarks of Nintendo, The Pokémon
Company, Creatures Inc. and GAME FREAK inc. "PokéBonk" is the name of an unofficial fan game
by Charcher. This project uses those names only to refer to the software it wraps.

## Third-party components

| Component | License | Role |
|---|---|---|
| [Electron](https://www.electronjs.org) | MIT | Application shell |
| [Chromium](https://www.chromium.org) | BSD-3-Clause and others | Rendering engine bundled by Electron |
| [electron-builder](https://www.electron.build) | MIT | Packaging (build-time only) |
| [electron-updater](https://github.com/electron-userland/electron-builder) | MIT | Self-update (build-time only) |

The game itself uses [three.js](https://threejs.org) (MIT) and is distributed by its own author
under its own terms.

## Distribution

The client is provided as-is, with no warranty. You are responsible for complying with the
upstream game's terms and with the laws that apply to you.
