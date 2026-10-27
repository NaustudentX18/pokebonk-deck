# PokéBonk Deck — Design Spec

**Date:** 2026-10-27
**Status:** Approved for implementation (research complete, stack decided)
**Repo:** `~/Work/projects/pokebonk-deck` → GitHub `NaustudentX18/pokebonk-deck`
**Supersedes:** nothing — greenfield

---

## 1. Problem

PokéBonk is a browser game (`https://pokebonk.com`) — a 3D Pokémon survivor roguelite built
with Three.js and served as a Vite-bundled ES-module app. It ships daily. The upstream
developer's legal page states the game is *only* distributed as a website.

On a phone this is solved by wrapping the URL in a WebView APK. On a Steam Deck the same
problem exists and is worse: a browser tab has no kiosk mode, no persistent origin storage by
default, no console-style launch, and the Steam Deck's controller has to survive a browser's
chrome, URL bar, and Steam Input's Desktop layout.

**Goal:** a native Linux application for Steam Deck (SteamOS 3) that runs PokéBonk as a
first-class console app — fullscreen, controller-native, save-persistent — and that picks up
upstream game updates without the user doing anything.

**Non-goals:**
- Not a re-implementation or port of the game. The game source is not public.
- Not an offline copy. PokéBonk has no service worker and its accounts/rankings/seasons live
  on `api.pokebonk.com`; offline play would require mirroring the assets and re-implementing
  the backend. Out of scope, and it would violate the upstream licensing intent.
- Not a Steam Store release. No Steamworks integration, no Valve review.
- Not a general-purpose webview browser. One target URL, one game.

---

## 2. Evidence base

Every load-bearing claim below was verified against live sources on 2026-10-27, not recalled.

### 2.1 The game (measured)

| Fact | How it was established |
|---|---|
| Canonical URL is `https://pokebonk.com/` | Many clone sites exist (`pokebonk.gg`, `.im`, `.top`, `pokebonk.io`). Only `.com` is the original; the creator warns against lookalikes on Discord. |
| Build id `mvpt1dlr`, version `0.8.59` (2026-10-26) | `GET https://pokebonk.com/version.json` → `{"build":"mvpt1dlr","version":"0.8.59"}` |
| Build id also in `<meta name="pokebonk-build">` | Fetched `index.html`, parsed |
| **No service worker** — not offline-capable | `/sw.js`, `/service-worker.js`, `/pwa-sw.js` all HTTP 404; zero `serviceWorker`/`workbox` matches in the bundles |
| Manifest exists, `display: fullscreen`, `orientation: landscape` | `GET /manifest.webmanifest` |
| **Cannot be iframed** | `Content-Security-Policy: frame-ancestors 'self'` and `X-Frame-Options: SAMEORIGIN` on every response, including `/assets/*` and `/version.json` |
| Saves are `localStorage` on the `https://pokebonk.com` origin | Grep of `main-D9lomsK5-mvpt1dlr.js`: no `indexedDB`, no `caches.`, no `document.cookie`. Keys: `pb.session`, `pb.guest`, `pb.last`, `pb.device`, `pb.seenVersion`, `pb.news.seen`, `pb-rstick:<gamepadId>`, `pokebonk.theme`, `pokebonk.touch`, `pokebonk.buildPlan.*`, `pokebonk.archivePresets.*`, `pb-fs-off`, `pb-battery` |
| Accounts sync to `api.pokebonk.com` with `Authorization: Bearer` + `X-Device` + `X-Client: 2` | Bundle inspection |
| **Full Gamepad API support** | `navigator.getGamepads?.()` polled every frame; `gamepadconnected`/`gamepaddisconnected` handled; three layouts detected — `std`, `xlinux` (`/xbox|xinput|045e|gamesir|microsoft|steam/i`), `generic` |
| Controller button map | `ya={jump:0,dash:1,interact:2,ult:3,lock:5,aim:4,confirm:0,back:1,reroll:2,skip:3,banish:5}` |
| Keyboard defaults | `_a={up:KeyW,down:KeyS,left:KeyA,right:KeyD,jump:Space,dash:ShiftLeft,interact:KeyE,ult:KeyR,lock:Mouse2,aim:KeyQ,autorun:KeyT,map:KeyM,autoult:KeyY,pause:KeyP,reroll:KeyF,skip:KeyX,banish:KeyZ}` |
| The game detects software rasterisers and warns | `var Tl=/swiftshader\|llvmpipe\|softpipe\|software\|basic render\|microsoft basic/i` → shows "Your browser is not using your graphics card" |
| Game polls `version.json` itself and shows a reload banner | `yF()` compares against the compiled-in build id; `bF()` tears down the renderer and navigates with `?v=<newBuild>` |

### 2.2 The Deck (verified)

| Fact | Source |
|---|---|
| SteamOS 3 ships every Electron/Chromium Linux runtime dep (nss, at-spi2, gtk3, mesa, libdrm, cups, xss, xkbcommon, alsa, pipewire, X11 stack) | SteamOS 3.8.14 package list |
| `kernel.unprivileged_userns_clone=1` — Electron's namespace sandbox works, no `--no-sandbox` needed | Arch/SteamOS defaults; SteamOS's own Flatpak stack depends on it |
| Steam Input's virtual pad appears as a real `/dev/input/js0` node | Real Steam Deck system log (SteamOS 3.7.19): `input: Microsoft X-Box 360 pad 0 as /devices/virtual/input/input40` |
| Chromium on Linux polls **joydev** (`/dev/input/js*`), not evdev, for buttons/axes | `gamepad_platform_data_fetcher_linux.cc` @ Chromium 156 |
| `js*` nodes are mode `0664` (world-readable) by systemd's `50-udev-default.rules` | systemd source |
| The Electron 27+ "Steam Input breaks gamepads" issue is **Windows-only** | electron#45732 and #45989 are both labelled `platform/windows`; the underlying Chromium change (M114 `4aa5edf6d967`) is a Windows Xbox-Input fetcher. Linux's joydev path is untouched. Valve's own fix (Steam client, 9 Sept 2025) was likewise Windows-scoped |
| **Electron 45 is the first Electron release with Valve's hid-steam mappings** | Chromium M156 added `MapperValve2` for the Steam Deck (PID 1205) and the Steam Controller 2026 (CL 8311577, 2026-09-10). Electron 45 branched from M156 on 2026-09-28 |
| Chromium hides gamepads until the user presses a button | `gamepad_service.cc` @156: `did_observe_user_gesture` → `RegisterForUserGesture` |
| Valve is dropping FUSE2 from SteamOS | SteamOS issue #2391 (open) |
| Launching from Steam runs the app inside the Steam Linux Runtime container | Since Nov 2024 native Linux titles run in SLR 1.0 (scout) by default. `pressure-vessel` shares `/dev` and exposes read-only `/run/udev`, so controllers **already connected at launch are detected** — which is the Deck's normal case — but **hotplug** is unreliable in the container. Verify `ls /dev/input` and `ls /run/udev` inside the container before blaming the code |

### 2.3 Local proof (measured on this machine, 2026-10-27)

- Electron 45.0.0 (Chromium 156) loads `https://pokebonk.com/` and boots the real game:
  `webgl2: true`, renderer `ANGLE (Intel, Mesa Intel(R) UHD Graphics 630 (CFL GT2), OpenGL ES 3.2)`,
  build `mvpt1dlr`, guest session persisted a `pb.device` key to `localStorage`.
- `electron-builder --linux AppImage` produces a **117 MB** AppImage with the **static,
  FUSE3-free** runtime (`toolsets.appimage: 1.0.3`) — confirmed by `ldd` on the extracted
  `AppRun`: no `libfuse` linkage — and an embedded block map for differential updates.
- Screenshots and gameplay video in `site/media/` are **real captures** of the live game
  (see `tools/capture-final.js`): title screen, partner select, hub, League/Pokédex, live 3D
  gameplay in Viridian Forest, and a 15-second gameplay video encoded to H.264 + VP9.
- **The plan's build configuration was executed end-to-end and produced a working AppImage.**
  Building with the exact `package.json` from the implementation plan produced
  `dist/PokebonkDeck-1.0.0-x86_64.AppImage` (113 MB) with `latest-linux.yml`, and the
  verification script confirmed the static FUSE3-free runtime with conditional sandbox
  handling. Four defects were found by that validation and fixed in the plan:
  `desktopName` must be top-level `package.json` metadata (not a `build` key);
  `syncDesktopName` belongs under `build.linux`; `latest-linux.yml` is only emitted when a
  publish provider is configured, so the GitHub provider needs `GH_TOKEN`; and a naive
  `grep -- '--no-sandbox'` on `AppRun` is a false positive because the static runtime
  mentions that flag inside its conditional user-namespace probe.

### 2.4 Alternatives rejected

| Option | Why not |
|---|---|
| **Tauri / wry / WebKitGTK** | WebKitGTK has Gamepad API via libmanette, but button mapping falls back to a *modulo* for unmapped codes, haptics are unimplemented, and WebKitGTK is not present on SteamOS (would have to be bundled). Chromium is the engine the game's own `xlinux` layout branch targets. |
| **Offline mirror** (as `VdustR/pokebonk-offline` does) | Requires mirroring every asset and re-implementing `api.pokebonk.com`; upstream ships daily, so the mirror needs its own CI; it redistributes assets the upstream explicitly does not distribute. |
| **Flatpak as primary channel** | `electron-builder`'s flatpak target emits only a single-file bundle, which is **not updatable**. A real OSTree remote would need hosting + GPG signing. |
| **Proton / Windows build** | That is exactly the code path where Electron ≥27 loses the Gamepad API. Native Linux only. |

---

## 3. Architecture

```
┌─ AppImage (static runtime, FUSE3-free, ~118 MB) ────────────────────┐
│  main.js — Electron 45 main process                                 │
│    ├─ creates BrowserWindow: kiosk, 1280×800, no menu                │
│    ├─ persistent session partition (localStorage survives restarts)  │
│    ├─ GamepadWatcher: polls navigator.getGamepads() after a gesture  │
│    ├─ UpdateProbe: GET /version.json in main process (no CORS)      │
│    │     → if build != lastBuild → reload webview with ?v=<build>  │
│    ├─ ShellUpdater: electron-updater AppImageUpdater (self-update)  │
│    └─ MenuOverlay: in-app shell menu (resume / fullscreen / reload)  │
│  preload.js — contextBridge: exposes __deck.{reload,quit,menu}      │
│  renderer = https://pokebonk.com/ (top-level document)              │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.1 Module boundaries

| File | Responsibility |
|---|---|
| `src/main.js` | Process lifecycle, window creation, wiring. No game logic. |
| `src/window.js` | BrowserWindow factory: kiosk, background colour, partition, load URL. |
| `src/version-probe.js` | Fetch `version.json` out-of-process, diff build ids, emit `update-available`. Pure function + one HTTP call, no Electron imports → unit-testable. |
| `src/gamepad-watcher.js` | Polls `navigator.getGamepads()` on an interval, filters Steam ghost pads, emits `pad-connected`/`pad-disconnected`. Isolated so the gesture gate is handled in one place. |
| `src/shell-updater.js` | Wraps `electron-updater`; reports state as `idle`/`checking`/`available`/`downloaded`/`error`. |
| `src/menu.js` | Builds the shell overlay window (frameless HTML) and routes commands back to `main.js`. |
| `src/preload.js` | `contextBridge` surface. `sandbox: false` — Electron 45 sandboxed preloads lost `Buffer`/`events`/`timers` shims, and this preload needs none of them, so the default is fine; explicit `sandbox: false` only if a dependency demands it. |

### 3.2 Data flow

1. **Launch** → window created in kiosk mode → `https://pokebonk.com/` loads.
2. **Gesture gate** → Chromium exposes no gamepad until the user presses a button. The watcher
   polls; on first non-null pad it emits `pad-connected` and the shell reveals the "press any
   button" prompt dismissal.
3. **Update check** → main process `fetch('https://pokebonk.com/version.json')` (no CORS
   header on that endpoint, so it must be out-of-process). If `build` differs from the id the
   shell last saw, the shell prompts and reloads the webview with `?v=<build>`, mirroring the
   game's own `bF()` teardown: stop the animation loop, dispose the renderer, force context
   loss, then navigate.
4. **Shell self-update** → `electron-updater`'s `AppImageUpdater` polls the release channel;
   the new AppImage replaces the running one atomically on next launch. Requires `APPIMAGE`
   to be set in the environment (true only when launched as an AppImage) and the file to sit
   on a writable, same-filesystem path (internal storage — **not** a FAT32 SD card).
5. **Quit** → `before-quit` writes the last-seen build id to the user-data dir.

### 3.3 Explicit non-goals in code

- No asset bundling, no offline mirror, no API shim.
- No `User-Agent` rewriting, no `Origin`/`Referer` rewriting — Cloudflare sits in front.
- No telemetry, no crash reporter that phones home.
- No `--no-sandbox`, no `--disable-gpu`.

---

## 4. Packaging & distribution

| Channel | Artifact | Update mechanism | Status |
|---|---|---|---|
| **Primary** | `PokebonkDeck-<version>-x86_64.AppImage` | `electron-updater` `AppImageUpdater` — in-app, automatic | shipped |
| Secondary | Source tarball / `npm run start` | manual | shipped |
| Not shipped | Flatpak bundle | bundles are not updatable | deferred |

Build config pins that matter:

- `toolsets: { appimage: "1.0.3" }` — the static, FUSE3-free runtime. electron-builder v26
  otherwise ships the legacy FUSE2 runtime **and force-injects `--no-sandbox`**, which would
  both break when Valve drops FUSE2 and disable the Chromium sandbox.
- `desktopName` + `linux.syncDesktopName: true` — so the Wayland window is associated with the
  `.desktop` entry.
- No `--no-sandbox` in `linux.executableArgs` (it leaks into other targets).

---

## 5. Landing page

`site/` — static HTML + CSS, no build step, GitHub Pages–ready. Same house style as
`portable-agent/site`.

Content is **verified against the live game**, not invented:

- **Photos** — real captures of the title screen, partner select, hub, League/Pokédex screen
  and live 3D gameplay.
- **Video** — real gameplay, recorded from the game canvas via `MediaRecorder`, re-encoded to
  H.264 MP4 (`faststart`) + VP9 WebM, with a poster frame.
- **Logos** — an original SVG mark for this project (a stylised Poké Ball + Deck controller).
  No Nintendo/GitHub artwork is copied; the game's own title card appears only inside the
  screenshots, as identification.
- **Controls table** — the game's real default keymap and button map, read from the bundle.
- **Tips** — six concrete pieces of advice (stick-learning wizard, passive-first partner picks,
  ultimate timing, draft shortcuts `F`/`X`/`Z`, auto-run + map, Deck storage hygiene).
- **Disclaimer** — unofficial, unaffiliated, no assets redistributed.

---

## 6. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Chromium's Gamepad API needs a user gesture before reporting a pad | Medium | Watcher polls rather than trusting `gamepadconnected`; the shell's first screen is a "press any button" prompt |
| Steam Input's Desktop layout instead of Gamepad layout | Medium | Steam Input **cannot** be disabled for the Deck's built-in controller — the correct fix is to select the **Gamepad** action set and run in Game Mode (gamescope). Document it; ship a one-line diagnostic in the shell menu (`js0` node present? pad id?) |
| SteamOS drops FUSE2 | Low | Static AppImage runtime — FUSE3-free, no `libfuse` dependency |
| `APPIMAGE` env unset → updater inert | Low | Document launching the `.AppImage` directly; warn in the shell when `electron-updater` reports inactive |
| Upstream game changes break the client | Low | The client is a thin loader; it fails soft (the page still renders) |
| Cloudflare challenges a custom UA | Low | Do not rewrite the UA |
| The game detects software rendering and warns | Low | Do not disable hardware acceleration; on the Deck, Mesa provides it natively |

---

## 7. Acceptance criteria

1. `npm run build` produces an AppImage; `ldd` on the extracted `AppRun` shows no `libfuse`.
2. The app launches on Steam Deck, goes fullscreen at 1280×800, and the game is playable with
   the Deck controller.
3. `localStorage` persists across restarts (`pb.device` survives a quit/relaunch).
4. When the upstream build id changes, the client detects it and offers a reload that lands on
   the new build.
5. The shell self-updates from the release channel when a newer AppImage is published.
6. `site/index.html` renders at 390 px and 1440 px with no horizontal overflow; every image and
   the video resolve; all internal links resolve.
7. The landing page contains no fabricated claims: every number, keybinding, and version is
   traceable to a capture or a source file.
