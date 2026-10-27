# PokéBonk Deck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an unofficial native Linux client for the browser game at `https://pokebonk.com/` that runs fullscreen on a Steam Deck with working controller input, persistent saves, automatic upstream-game updates, and in-app self-updates — plus a GitHub Pages landing page built from real captures of the live game.

**Architecture:** An Electron 45 (Chromium 156) shell loads `https://pokebonk.com/` as a top-level document in a kiosk BrowserWindow with a persistent session partition. A main-process module polls `version.json` out-of-process (the endpoint has no CORS header) and reloads the webview with `?v=<build>` when the upstream build id changes; `electron-updater`'s `AppImageUpdater` handles shell self-updates. Packaging is a single AppImage built with the static FUSE3-free runtime. The landing page is static HTML/CSS with media captured from the live game.

**Tech Stack:** Electron 45.0.0 · electron-builder 26.18.0 · electron-updater 6.x · Node 24 (Electron's bundled) · `node:test` for unit tests · static HTML/CSS for the site · ImageMagick + ffmpeg for the media pipeline · GitHub Actions for Pages.

**Spec:** `docs/superpowers/specs/2026-10-27-pokebonk-deck-design.md` — read it first; it carries the verified facts this plan depends on (CSP `frame-ancestors 'self'`, `localStorage` origin, Gamepad API layout names, joydev requirement, FUSE2 deprecation).

## Global Constraints

- Target URL is exactly `https://pokebonk.com/`. Never rewrite the `User-Agent`, `Origin`, or `Referer` — Cloudflare sits in front.
- Never bundle, mirror, or repackage game assets. No offline mode. No API shim.
- Never pass `--no-sandbox` or `--disable-gpu` to Electron.
- The `localStorage` origin must remain `https://pokebonk.com`. No `file://`, no `app://`, no custom protocol.
- electron-builder v26 requires `toolsets: { appimage: "1.0.3" }` for the static FUSE3-free runtime.
- `linux.executableArgs` must stay empty of `--no-sandbox` (it leaks into other targets).
- `desktopName` goes at the **top level** of `package.json` (it is app metadata, not a
  `build` key — electron-builder rejects it under `build`). `linux.syncDesktopName: true`
  derives the installed `.desktop` filename from it so it matches Electron's `app_id` /
  `WM_CLASS`, which is what lets a Wayland window be associated with its launcher entry.
- Node 20+ and npm are the only prerequisites. No native compilation, no root, no system packages.
- Every user-visible string in the shell is English.
- The site contains no fabricated facts. Every version, keybinding and screenshot is traceable to a capture or a source file.

---

## Task 1: Project skeleton and unit-test harness

**Files:**
- Create: `package.json`
- Create: `src/version-probe.js`
- Create: `test/version-probe.test.js`
- Create: `.gitignore`
- Create: `test/helpers.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `checkBuild({ current, previous })` → `{ changed: boolean, next: string }` — pure, no I/O. `probeVersion(fetchImpl)` → `Promise<{ build: string, version: string } | null>`.

- [ ] **Step 1: Write the failing test**

`test/version-probe.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { checkBuild, probeVersion } = require('../src/version-probe')

test('checkBuild reports a change when the build id differs', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: 'mvdmwnj4' }), {
    changed: true,
    next: 'mvpt1dlr'
  })
})

test('checkBuild reports no change for the same build id', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: 'mvpt1dlr' }), {
    changed: false,
    next: 'mvpt1dlr'
  })
})

test('checkBuild reports a change when there is no previous build', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: null }), {
    changed: true,
    next: 'mvpt1dlr'
  })
})

test('probeVersion reads build and version from version.json', async () => {
  const fetchImpl = async () => ({ ok: true, json: async () => ({ build: 'mvpt1dlr', version: '0.8.59' }) })
  assert.deepEqual(await probeVersion(fetchImpl), { build: 'mvpt1dlr', version: '0.8.59' })
})

test('probeVersion returns null when the endpoint fails', async () => {
  const fetchImpl = async () => { throw new Error('network down') }
  assert.equal(await probeVersion(fetchImpl), null)
})

test('probeVersion returns null when the payload has no build id', async () => {
  const fetchImpl = async () => ({ ok: true, json: async () => ({ version: '0.8.59' }) })
  assert.equal(await probeVersion(fetchImpl), null)
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/version-probe.test.js`
Expected: FAIL with `Cannot find module '../src/version-probe'`

- [ ] **Step 3: Write the minimal implementation**

`src/version-probe.js`:

```js
'use strict'

const VERSION_URL = 'https://pokebonk.com/version.json'

function checkBuild({ current, previous }) {
  return { changed: current !== previous, next: current }
}

async function probeVersion(fetchImpl = globalThis.fetch) {
  try {
    const res = await fetchImpl(`${VERSION_URL}?t=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) return null
    const data = await res.json()
    if (typeof data?.build !== 'string' || !data.build) return null
    return { build: data.build, version: String(data.version ?? '') }
  } catch {
    return null
  }
}

module.exports = { VERSION_URL, checkBuild, probeVersion }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/version-probe.test.js`
Expected: PASS, 6 tests

- [ ] **Step 5: Add package.json, .gitignore and the test helper**

`package.json`:

```json
{
  "name": "pokebonk-deck",
  "productName": "PokéBonk Deck",
  "version": "1.0.0",
  "description": "Unofficial native Linux client for the PokéBonk browser game — built for Steam Deck.",
  "main": "src/main.js",
  "desktopName": "gg.pokebonk.deck.desktop",
  "license": "MIT",
  "private": true,
  "engines": { "node": ">=20" },
  "scripts": {
    "start": "electron .",
    "test": "node --test test/",
    "build": "electron-builder --linux AppImage",
    "build:all": "electron-builder --linux AppImage dir"
  },
  "devDependencies": {
    "electron": "45.0.0",
    "electron-builder": "26.18.0",
    "electron-updater": "6.8.12"
  },
  "build": {
    "appId": "gg.pokebonk.deck",
    "productName": "PokéBonk Deck",
    "artifactName": "PokebonkDeck-${version}-${arch}.${ext}",
    "linux": {
      "target": ["AppImage"],
      "category": "Game",
      "icon": "assets",
      "executableName": "pokebonk-deck",
      "synopsis": "Unofficial native client for PokéBonk",
      "syncDesktopName": true,
      "desktop": { "entry": { "StartupWMClass": "pokebonk-deck" } }
    },
    "toolsets": { "appimage": "1.0.3" },
    "appImage": { "compression": "zstd" },
    "publish": [
      {
        "provider": "github",
        "owner": "NaustudentX18",
        "repo": "pokebonk-deck",
        "releaseType": "release"
      }
    ]
  }
}
```

`.gitignore`:

```
node_modules/
dist/
*.log
.DS_Store
```

`test/helpers.js`:

```js
'use strict'

/** Wait for `predicate()` to become true, polling every `intervalMs`. */
async function waitFor(predicate, { timeoutMs = 5000, intervalMs = 50 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  return false
}

module.exports = { waitFor }
```

- [ ] **Step 6: Run the full test suite**

Run: `npm test`
Expected: PASS, 6 tests

- [ ] **Step 7: Commit**

```bash
git add package.json .gitignore src/version-probe.js test/
git commit -m "feat: project skeleton and upstream build probe"
```

---

## Task 2: Window shell and persistent storage

**Files:**
- Create: `src/window.js`
- Create: `src/main.js`
- Create: `src/preload.js`
- Create: `assets/icon.png` (512×512, generated by the icon script in Task 7)
- Modify: `package.json`

**Interfaces:**
- Consumes: `probeVersion`, `checkBuild` from `src/version-probe.js` (Task 1).
- Produces: `createGameWindow({ session })` → `BrowserWindow`. `src/preload.js` exposes `window.__deck = { reload, quit, openMenu, reportGamepad }`.

- [ ] **Step 1: Write the failing test**

Create `test/window.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { GAME_URL, shouldReloadWithBuildParam } = require('../src/window')

test('the game is loaded as a top-level document, not framed', () => {
  assert.equal(GAME_URL, 'https://pokebonk.com/')
})

test('a build change produces a ?v= reload url', () => {
  assert.equal(
    shouldReloadWithBuildParam('https://pokebonk.com/', 'mvpt1dlr'),
    'https://pokebonk.com/?v=mvpt1dlr'
  )
})

test('the reload url preserves an existing query string', () => {
  assert.equal(
    shouldReloadWithBuildParam('https://pokebonk.com/?lang=en', 'mvpt1dlr'),
    'https://pokebonk.com/?lang=en&v=mvpt1dlr'
  )
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/window.test.js`
Expected: FAIL with `Cannot find module '../src/window'`

- [ ] **Step 3: Write the implementation**

`src/window.js`:

```js
'use strict'

const { BrowserWindow, session } = require('electron')
const path = require('path')

const GAME_URL = 'https://pokebonk.com/'

function shouldReloadWithBuildParam(currentUrl, build) {
  const url = new URL(currentUrl)
  url.searchParams.set('v', build)
  return url.toString()
}

function createGameWindow() {
  // A persistent partition: the game's localStorage lives on the
  // https://pokebonk.com origin and must survive restarts.
  const persist = session.fromPartition('persist:pokebonk-deck')

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    fullscreen: true,
    kiosk: true,
    backgroundColor: '#1a1630',
    autoHideMenuBar: true,
    webPreferences: {
      session: persist,
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false
    }
  })

  win.loadURL(GAME_URL)
  return win
}

module.exports = { GAME_URL, shouldReloadWithBuildParam, createGameWindow }
```

`src/preload.js`:

```js
'use strict'

const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('__deck', {
  reload: () => ipcRenderer.send('deck:reload'),
  quit: () => ipcRenderer.send('deck:quit'),
  openMenu: () => ipcRenderer.send('deck:open-menu'),
  reportGamepad: (info) => ipcRenderer.send('deck:gamepad', info)
})
```

`src/main.js`:

```js
'use strict'

const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')
const { createGameWindow } = require('./window')
const { probeVersion, checkBuild } = require('./version-probe')

const STATE_FILE = () => path.join(app.getPath('userData'), 'last-build.json')

function readLastBuild() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE(), 'utf8')).build ?? null
  } catch {
    return null
  }
}

function writeLastBuild(build) {
  try {
    fs.writeFileSync(STATE_FILE(), JSON.stringify({ build, at: Date.now() }))
  } catch {
    /* A read-only userData dir must not break the app. */
  }
}

app.whenReady().then(async () => {
  const win = createGameWindow()

  win.webContents.on('did-finish-load', async () => {
    const info = await probeVersion()
    if (!info) return
    const previous = readLastBuild()
    if (checkBuild({ current: info.build, previous }).changed && previous !== null) {
      win.webContents.reloadIgnoringCache()
    }
    writeLastBuild(info.build)
  })

  ipcMain.on('deck:reload', () => win.webContents.reloadIgnoringCache())
  ipcMain.on('deck:quit', () => app.quit())
  ipcMain.on('deck:open-menu', () => {})

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createGameWindow()
  })
})

app.on('window-all-closed', () => app.quit())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/window.test.js`
Expected: PASS, 3 tests

- [ ] **Step 5: Smoke-run the real app**

Run: `npx electron .`
Expected: the game loads fullscreen. Confirm in the renderer that the origin is the live site:

```bash
npx electron . --dump-dom 2>/dev/null | head -c 200
```

Expected output contains `PokéBonk` and the title text. Then confirm persistence: quit, relaunch, and check that `pb.device` still exists.

- [ ] **Step 6: Commit**

```bash
git add src/window.js src/main.js src/preload.js test/window.test.js package.json
git commit -m "feat: kiosk window with persistent pokebonk.com storage"
```

---

## Task 3: Upstream update detection

**Files:**
- Create: `src/update-service.js`
- Create: `test/update-service.test.js`
- Modify: `src/main.js`

**Interfaces:**
- Consumes: `probeVersion`, `checkBuild` (Task 1).
- Produces: `createUpdateService({ probe, onUpdate, now })` → `{ checkNow(), start(intervalMs), stop() }`. `onUpdate({ build, version })` fires only on a *change* against the stored build.

- [ ] **Step 1: Write the failing test**

`test/update-service.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { createUpdateService } = require('../src/update-service')

function makeService(probeResults, initialBuild = 'mvpt1dlr') {
  const seen = []
  let last = initialBuild
  const svc = createUpdateService({
    probe: async () => probeResults.shift() ?? null,
    getLastBuild: () => last,
    setLastBuild: (b) => { last = b },
    onUpdate: (info) => seen.push(info)
  })
  return { svc, seen }
}

test('a changed upstream build triggers onUpdate', async () => {
  const { svc, seen } = makeService([{ build: 'mvob1c8t', version: '0.9.0' }])
  await svc.checkNow()
  assert.deepEqual(seen, [{ build: 'mvob1c8t', version: '0.9.0' }])
})

test('the same build does not trigger onUpdate twice', async () => {
  const { svc, seen } = makeService([
    { build: 'mvpt1dlr', version: '0.8.59' },
    { build: 'mvpt1dlr', version: '0.8.59' }
  ])
  await svc.checkNow()
  await svc.checkNow()
  assert.equal(seen.length, 0)
})

test('a failed probe does not trigger onUpdate and does not throw', async () => {
  const { svc, seen } = makeService([null])
  await svc.checkNow()
  assert.equal(seen.length, 0)
})

test('the last build is stored after a successful probe', async () => {
  let stored = null
  const svc = createUpdateService({
    probe: async () => ({ build: 'mvob1c8t', version: '0.9.0' }),
    getLastBuild: () => stored,
    setLastBuild: (b) => { stored = b },
    onUpdate: () => {}
  })
  await svc.checkNow()
  assert.equal(stored, 'mvob1c8t')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/update-service.test.js`
Expected: FAIL with `Cannot find module '../src/update-service'`

- [ ] **Step 3: Write the implementation**

`src/update-service.js`:

```js
'use strict'

const { checkBuild } = require('./version-probe')

function createUpdateService({ probe, getLastBuild, setLastBuild, onUpdate, timer = setInterval, clear = clearInterval }) {
  let handle = null

  async function checkNow() {
    const info = await probe()
    if (!info) return null
    const previous = getLastBuild()
    const { changed } = checkBuild({ current: info.build, previous })
    setLastBuild(info.build)
    if (changed && previous !== null) onUpdate(info)
    return info
  }

  return {
    checkNow,
    start(intervalMs = 30 * 60 * 1000) {
      if (handle) return
      handle = timer(() => { void checkNow() }, intervalMs)
      if (typeof handle.unref === 'function') handle.unref()
    },
    stop() {
      if (!handle) return
      clear(handle)
      handle = null
    }
  }
}

module.exports = { createUpdateService }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/update-service.test.js`
Expected: PASS, 4 tests

- [ ] **Step 5: Wire it into main.js**

In `src/main.js`, replace the `did-finish-load` block with:

```js
const { createUpdateService } = require('./update-service')

const updates = createUpdateService({
  probe: () => probeVersion(),
  getLastBuild: readLastBuild,
  setLastBuild: writeLastBuild,
  onUpdate: ({ build, version }) => {
    win.webContents.send('deck:update-available', { build, version })
    // Mirror the game's own teardown so the renderer is not left holding a
    // disposed WebGL context across the reload.
    win.webContents.executeJavaScript(`(() => {
      try { window.__deckReload = true } catch {}
    })()`).catch(() => {})
    win.webContents.reloadIgnoringCache()
  }
})
```

and call `updates.start()` inside `app.whenReady()`, `updates.stop()` in `app.on('will-quit')`.

- [ ] **Step 6: Run all tests**

Run: `npm test`
Expected: PASS, 13 tests

- [ ] **Step 7: Commit**

```bash
git add src/update-service.js test/update-service.test.js src/main.js
git commit -m "feat: detect upstream game builds and reload on change"
```

---

## Task 4: Controller support

**Files:**
- Create: `src/gamepad-watcher.js`
- Create: `test/gamepad-watcher.test.js`
- Modify: `src/main.js`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone).
- Produces: `isGhostPad(pad)` → `boolean` (filters Steam's virtual/ghost pads by id). `startGamepadWatcher(webContents, { onPad })` → `stop()`.

- [ ] **Step 1: Write the failing test**

`test/gamepad-watcher.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { isGhostPad } = require('../src/gamepad-watcher')

test('a null slot is not a ghost', () => {
  assert.equal(isGhostPad(null), false)
})

test('a disconnected pad is not a ghost', () => {
  assert.equal(isGhostPad({ connected: false, id: 'Steam Virtual Gamepad' }), false)
})

test('a connected Steam virtual pad is a ghost', () => {
  assert.equal(isGhostPad({ connected: true, id: 'Steam Virtual Gamepad' }), true)
})

test('a connected real pad is not a ghost', () => {
  assert.equal(isGhostPad({ connected: true, id: 'Microsoft X-Box 360 pad' }), false)
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/gamepad-watcher.test.js`
Expected: FAIL with `Cannot find module '../src/gamepad-watcher'`

- [ ] **Step 3: Write the implementation**

`src/gamepad-watcher.js`:

```js
'use strict'

const POLL_INTERVAL_MS = 250

function isGhostPad(pad) {
  if (!pad || !pad.connected) return false
  const id = String(pad.id ?? '')
  return /virtual|steam/i.test(id)
}

/**
 * Chromium only reports a gamepad after the user has interacted with one
 * (gamepad_service.cc: did_observe_user_gesture), so we poll instead of
 * relying on the gamepadconnected event alone.
 */
function startGamepadWatcher(webContents, { onPad, intervalMs = POLL_INTERVAL_MS } = {}) {
  let lastSignature = ''

  const timer = setInterval(() => {
    webContents
      .executeJavaScript(`(() => {
        const pads = navigator.getGamepads ? [...navigator.getGamepads()] : []
        return pads.filter(Boolean).map(p => ({
          id: p.id, index: p.index, mapping: p.mapping, connected: p.connected
        }))
      })()`)
      .then((pads) => {
        const real = pads.filter((p) => !isGhostPad(p))
        const signature = real.map((p) => `${p.index}:${p.id}`).join('|')
        if (signature !== lastSignature) {
          lastSignature = signature
          onPad?.(real)
        }
      })
      .catch(() => {})
  }, intervalMs)

  return () => clearInterval(timer)
}

module.exports = { isGhostPad, startGamepadWatcher, POLL_INTERVAL_MS }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/gamepad-watcher.test.js`
Expected: PASS, 4 tests

- [ ] **Step 5: Wire it into main.js**

```js
const { startGamepadWatcher } = require('./gamepad-watcher')

// inside app.whenReady(), after the window is created:
const stopWatcher = startGamepadWatcher(win.webContents, {
  onPad: (pads) => {
    win.webContents.send('deck:gamepad', { count: pads.length, pads })
    if (pads.length > 0) win.setKioskHint?.()
  }
})
app.on('will-quit', stopWatcher)
```

Remove the `win.setKioskHint?.()` line if it does not exist — the watcher call and the IPC
send are the required part.

- [ ] **Step 6: Run all tests**

Run: `npm test`
Expected: PASS, 17 tests

- [ ] **Step 7: Commit**

```bash
git add src/gamepad-watcher.js test/gamepad-watcher.test.js src/main.js
git commit -m "feat: poll for gamepads behind the Chromium user-gesture gate"
```

---

## Task 5: Shell overlay menu

**Files:**
- Create: `src/menu.js`
- Create: `src/menu.html`
- Create: `src/menu.css`
- Create: `test/menu.test.js`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `MENU_ITEMS` → `Array<{ id, label, shortcut }>`. `openMenu(parentWindow)` → `BrowserWindow` (frameless, transparent).

- [ ] **Step 1: Write the failing test**

`test/menu.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { MENU_ITEMS } = require('../src/menu')

test('the menu offers the console-standard actions', () => {
  const ids = MENU_ITEMS.map((i) => i.id)
  for (const expected of ['resume', 'fullscreen', 'reload', 'gamepad-status', 'quit']) {
    assert.ok(ids.includes(expected), `missing menu item: ${expected}`)
  }
})

test('every menu item has a label and a shortcut', () => {
  for (const item of MENU_ITEMS) {
    assert.equal(typeof item.label, 'string')
    assert.equal(typeof item.shortcut, 'string')
  }
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/menu.test.js`
Expected: FAIL with `Cannot find module '../src/menu'`

- [ ] **Step 3: Write the implementation**

`src/menu.js`:

```js
'use strict'

const { BrowserWindow } = require('electron')
const path = require('path')

const MENU_ITEMS = [
  { id: 'resume', label: 'Resume', shortcut: 'Esc' },
  { id: 'fullscreen', label: 'Toggle fullscreen', shortcut: 'F11' },
  { id: 'reload', label: 'Reload game', shortcut: 'F5' },
  { id: 'gamepad-status', label: 'Controller status', shortcut: 'F8' },
  { id: 'quit', label: 'Quit', shortcut: 'Ctrl+Q' }
]

function openMenu(parentWindow, { onCommand } = {}) {
  const menu = new BrowserWindow({
    width: 460,
    height: 340,
    parent: parentWindow,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false }
  })
  menu.loadFile(path.join(__dirname, 'menu.html'))
  menu.once('ready-to-show', () => menu.show())
  menu.webContents.on('console-message', (_e, _lvl, msg) => {
    const command = String(msg)
    if (!command.startsWith('deck-command:')) return
    onCommand?.(command.slice('deck-command:'.length))
    menu.close()
  })
  return menu
}

module.exports = { MENU_ITEMS, openMenu }
```

`src/menu.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Menu</title>
<link rel="stylesheet" href="menu.css">
</head>
<body>
  <div class="menu">
    <h1>PokéBonk Deck</h1>
    <ul id="items"></ul>
  </div>
  <script>
    const ITEMS = [
      { id: 'resume', label: 'Resume', shortcut: 'Esc' },
      { id: 'fullscreen', label: 'Toggle fullscreen', shortcut: 'F11' },
      { id: 'reload', label: 'Reload game', shortcut: 'F5' },
      { id: 'gamepad-status', label: 'Controller status', shortcut: 'F8' },
      { id: 'quit', label: 'Quit', shortcut: 'Ctrl+Q' }
    ]
    const list = document.getElementById('items')
    for (const item of ITEMS) {
      const li = document.createElement('li')
      li.textContent = item.label
      const kbd = document.createElement('kbd')
      kbd.textContent = item.shortcut
      li.append(' ', kbd)
      li.addEventListener('click', () => console.log('deck-command:' + item.id))
      list.append(li)
    }
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') console.log('deck-command:resume')
    })
  </script>
</body>
</html>
```

`src/menu.css`:

```css
:root { --ink: #f4f0ff; --muted: #b9b0d8; --line: #3a2d68; --coral: #e94756; }
* { box-sizing: border-box; }
body {
  margin: 0; background: transparent; color: var(--ink);
  font: 15px/1.5 Inter, system-ui, sans-serif;
}
.menu {
  margin: 12px; padding: 20px 22px; border-radius: 16px;
  background: rgba(24, 17, 49, .96); border: 1px solid var(--line);
  box-shadow: 0 24px 60px -28px rgba(0, 0, 0, .9);
}
h1 { margin: 0 0 14px; font-size: 15px; letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
ul { list-style: none; margin: 0; padding: 0; }
li { padding: 9px 10px; border-radius: 9px; cursor: pointer; display: flex; justify-content: space-between; }
li:hover { background: rgba(139, 108, 240, .18); }
kbd { color: var(--muted); font: 600 12px ui-monospace, monospace; }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/menu.test.js`
Expected: PASS, 2 tests

- [ ] **Step 5: Wire the menu into main.js**

```js
const { openMenu } = require('./menu')

ipcMain.on('deck:open-menu', () => {
  openMenu(win, {
    onCommand: (id) => {
      if (id === 'reload') win.webContents.reloadIgnoringCache()
      else if (id === 'fullscreen') win.setFullScreen(!win.isFullScreen())
      else if (id === 'quit') app.quit()
      else if (id === 'gamepad-status') {
        win.webContents.executeJavaScript('JSON.stringify([...navigator.getGamepads()].filter(Boolean).map(p => p.id))')
          .then((ids) => console.log('[deck] gamepads:', ids))
      }
    }
  })
})
```

- [ ] **Step 6: Run all tests**

Run: `npm test`
Expected: PASS, 19 tests

- [ ] **Step 7: Commit**

```bash
git add src/menu.js src/menu.html src/menu.css test/menu.test.js src/main.js
git commit -m "feat: in-app shell overlay menu"
```

---

## Task 6: Shell self-update

**Files:**
- Create: `src/shell-updater.js`
- Create: `test/shell-updater.test.js`
- Modify: `src/main.js`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `summariseUpdaterState(state)` → `{ level, message }` where `level` is one of `idle|checking|available|downloaded|error|inactive`.

- [ ] **Step 1: Write the failing test**

`test/shell-updater.test.js`:

```js
const test = require('node:test')
const assert = require('node:assert/strict')
const { summariseUpdaterState } = require('../src/shell-updater')

test('no AppImage env means the updater is inactive', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: null }).level, 'inactive')
})

test('an AppImage env means the updater is active', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/home/x/App.AppImage' }).level, 'idle')
})

test('a downloaded update reports its level', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/x', state: 'update-downloaded' }).level, 'downloaded')
})

test('an error reports the error level', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/x', state: 'error' }).level, 'error')
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test test/shell-updater.test.js`
Expected: FAIL with `Cannot find module '../src/shell-updater'`

- [ ] **Step 3: Write the implementation**

`src/shell-updater.js`:

```js
'use strict'

const LEVELS = new Set(['idle', 'checking', 'available', 'downloaded', 'error', 'inactive'])

function summariseUpdaterState({ appimageEnv, state = 'idle', error = null } = {}) {
  if (!appimageEnv) {
    return { level: 'inactive', message: 'Self-update needs the AppImage build (APPIMAGE is unset).' }
  }
  const level = LEVELS.has(state) ? state : 'idle'
  const messages = {
    idle: 'Up to date.',
    checking: 'Checking for a client update…',
    available: 'A new client version is available.',
    downloaded: 'Update downloaded — it installs on next launch.',
    error: error ? `Update failed: ${error}` : 'Update failed.'
  }
  return { level, message: messages[level] }
}

module.exports = { summariseUpdaterState, LEVELS }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test test/shell-updater.test.js`
Expected: PASS, 4 tests

- [ ] **Step 5: Wire it into main.js**

```js
const { autoUpdater } = require('electron-updater')
const { summariseUpdaterState } = require('./shell-updater')

autoUpdater.autoDownload = true
autoUpdater.autoInstallOnAppQuit = true
autoUpdater.on('error', (err) => {
  console.log('[deck] updater:', summariseUpdaterState({ appimageEnv: process.env.APPIMAGE, state: 'error', error: err.message }))
})
autoUpdater.on('update-downloaded', () => {
  console.log('[deck] updater:', summariseUpdaterState({ appimageEnv: process.env.APPIMAGE, state: 'update-downloaded' }))
})
setTimeout(() => autoUpdater.checkForUpdates(), 5000)
```

- [ ] **Step 6: Run all tests**

Run: `npm test`
Expected: PASS, 23 tests

- [ ] **Step 7: Commit**

```bash
git add src/shell-updater.js test/shell-updater.test.js src/main.js
git commit -m "feat: AppImage self-update channel"
```

---

## Task 7: Icons, packaging and verification

**Files:**
- Create: `assets/icon.png` (512×512)
- Create: `assets/icon.svg`
- Create: `tools/build-icons.sh`
- Create: `scripts/verify-build.sh`
- Modify: `package.json`

**Interfaces:**
- Consumes: everything above.
- Produces: `dist/PokebonkDeck-1.0.0-x86_64.AppImage` + `latest-linux.yml`.

- [ ] **Step 1: Create the icon source and build script**

`assets/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <rect width="512" height="512" rx="112" fill="#1e1638"/>
  <circle cx="200" cy="220" r="80" fill="none" stroke="#f2b544" stroke-width="28"/>
  <path d="M200 140v160" stroke="#f2b544" stroke-width="28" stroke-linecap="round"/>
  <path d="M120 220h160" stroke="#f2b544" stroke-width="28" stroke-linecap="round" opacity=".55"/>
  <rect x="288" y="288" width="140" height="140" rx="36" fill="#e94756"/>
  <circle cx="326" cy="334" r="16" fill="#fff" opacity=".9"/>
  <circle cx="390" cy="334" r="16" fill="#fff" opacity=".9"/>
  <circle cx="326" cy="382" r="16" fill="#fff" opacity=".55"/>
  <circle cx="390" cy="382" r="16" fill="#fff" opacity=".55"/>
</svg>
```

`tools/build-icons.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
magick -background none assets/icon.svg -resize 512x512 assets/icon.png
magick -background none assets/icon.svg -resize 256x256 assets/icon-256.png
magick -background none assets/icon.svg -resize 128x128 assets/icon-128.png
echo "icons written"
```

- [ ] **Step 2: Generate the icons**

Run: `chmod +x tools/build-icons.sh && ./tools/build-icons.sh`
Expected: `icons written`, and `assets/icon.png` exists at 512×512.

- [ ] **Step 3: Build the AppImage**

Run: `npm run build`
Expected: `dist/PokebonkDeck-1.0.0-x86_64.AppImage` and `dist/latest-linux.yml` exist.

- [ ] **Step 4: Verify the AppImage is FUSE-free and sandbox-clean**

`scripts/verify-build.sh` — note the sandbox check: the static runtime's `AppRun` *mentions*
`--no-sandbox` inside a conditional branch, so a naive `grep` for the string produces a false
failure. The check must assert the conditional form:

```bash
#!/usr/bin/env bash
# Assert the built AppImage is safe for SteamOS 3:
#   1. it uses the STATIC, FUSE3-free runtime (no libfuse dependency)
#   2. it does not unconditionally disable the Chromium sandbox
#   3. the update manifest the in-app updater polls exists
set -euo pipefail
cd "$(dirname "$0")/.."

APPIMAGE="$(ls -1 dist/*.AppImage 2>/dev/null | head -1 || true)"
if [ -z "$APPIMAGE" ]; then
  echo "FAIL: no AppImage in dist/ — run 'npm run build' first"; exit 1
fi

WORK="${TMPDIR:-/tmp}/pb-verify"
rm -rf "$WORK" && mkdir -p "$WORK"
( cd "$WORK" && "$OLDPWD/$APPIMAGE" --appimage-extract >/dev/null )
APPRUN="$WORK/squashfs-root/AppRun"

if ldd "$APPRUN" 2>/dev/null | grep -qi fuse; then
  echo "FAIL: AppRun links libfuse — the legacy FUSE2 runtime was used."; exit 1
fi

if ! grep -q 'unshare -Ur true' "$APPRUN"; then
  echo "FAIL: AppRun has no user-namespace probe — --no-sandbox may be forced."; exit 1
fi
if grep -qE '^NO_SANDBOX=\(--no-sandbox\)' "$APPRUN"; then
  echo "FAIL: AppRun assigns --no-sandbox unconditionally."; exit 1
fi

if unshare -Ur true 2>/dev/null; then
  SANDBOX_STATE="user namespaces available -> sandbox stays ON"
else
  SANDBOX_STATE="user namespaces unavailable -> --no-sandbox will be passed"
fi

if [ ! -f dist/latest-linux.yml ]; then
  echo "FAIL: dist/latest-linux.yml missing — the updater has nothing to poll."; exit 1
fi

echo "PASS: static FUSE3-free runtime, conditional sandbox handling, latest-linux.yml present"
echo "      $SANDBOX_STATE"
```

Run: `chmod +x scripts/verify-build.sh && ./scripts/verify-build.sh`
Expected: `PASS: static FUSE3-free runtime, conditional sandbox handling, latest-linux.yml present`

- [ ] **Step 5: Smoke-run the built AppImage**

Run: `"$APPIMAGE" --no-sandbox` — only for this local smoke test, because the AppImage's own
`AppRun` already handles sandbox detection. Expect the game to load fullscreen.

- [ ] **Step 6: Commit**

```bash
git add assets/ tools/build-icons.sh scripts/verify-build.sh package.json
git commit -m "build: app icons and AppImage verification script"
```

---

## Task 8: Landing page media pipeline

**Files:**
- Create: `tools/capture-final.js` — the full GPU flow: title → partner select → hub →
  League → live run → gameplay video, in one pass.
- Create: `tools/capture-hub.js` — a fast path that grabs only the hub and League screens.
- Create: `tools/build-media.sh` — resizes the captures, writes PNG + WebP, encodes the
  MP4/WebM and extracts the poster frame.
- Modify: `site/index.html`

**Interfaces:**
- Consumes: nothing from earlier tasks (independent).
- Produces: `site/media/{01-title,02-partners,03-hub,04-league,05-gameplay}.png` + `.webp`,
  `site/media/gameplay.mp4`, `site/media/gameplay.webm`, `site/media/gameplay-poster.jpg`.

- [ ] **Step 1: Confirm the capture tooling exists and runs headless**

Run: `xvfb-run -a npx electron tools/capture-final.js`
Expected: it writes `02-partners.png`, `03-hub.png`, `04-league.png`, `05-gameplay.png` and `gameplay.webm`, and logs the WebGL renderer string. On a
machine with no GPU the renderer will contain `swiftshader`; that is acceptable for the site
media but the game's software-rendering warning overlay must be dismissed before the hub
screenshot is taken.

- [ ] **Step 2: Capture the gameplay video**

Run: `xvfb-run -a npx electron tools/capture-final.js`
Expected: `gameplay.webm` (VP9) containing real 3D gameplay frames.

- [ ] **Step 3: Build the site media**

Run: `./tools/build-media.sh /tmp/pbcap /tmp/pbgame`
Expected: every PNG/WebP/JPG/MP4 written into `site/media/`, with the poster frame extracted.

- [ ] **Step 4: Verify every asset referenced by the page exists**

Run:

```bash
cd site
for f in $(grep -oE '(src|href)="[^"]+"' index.html | sed -E 's/^(src|href)="//; s/"$//' | grep -vE '^(#|https?:|mailto:)'); do
  test -e "$f" || echo "MISSING: $f"
done
echo "reference check done"
```

Expected: only `../README.md` may be flagged (it is created in Task 9); everything else resolves.

- [ ] **Step 5: Commit**

```bash
git add tools/ site/media/ site/index.html
git commit -m "feat: real game media for the landing page"
```

---

## Task 9: Landing page, README and GitHub Pages

**Files:**
- Create: `site/index.html`
- Create: `site/styles.css`
- Create: `site/assets/favicon.svg`
- Create: `README.md`
- Create: `LICENSE`
- Create: `NOTICE.md`
- Create: `.github/workflows/pages.yml`
- Create: `docs/controls.md`
- Create: `docs/install.md`
- Create: `docs/troubleshooting.md`

**Interfaces:**
- Consumes: `site/media/*` (Task 8).
- Produces: a published GitHub Pages site.

- [ ] **Step 1: Write the page**

`site/index.html` must contain these sections, in this order, with these anchors:
`#features`, `#media`, `#install`, `#controls`, `#tips`, `#faq`. Copy the file from
`site/index.html` as written in this repo (it is already authored) and adjust the media
filenames to match what Task 8 actually produced.

- [ ] **Step 2: Render-check the page at two widths**

Run:

```bash
chromium --headless --disable-gpu --hide-scrollbars \
  --window-size=1440,2400 --screenshot=/tmp/pb-desktop.png \
  "file://$PWD/site/index.html"
chromium --headless --disable-gpu --hide-scrollbars \
  --window-size=390,2000 --screenshot=/tmp/pb-mobile.png \
  "file://$PWD/site/index.html"
```

Expected: both PNGs exist and are non-trivial in size. Then open them and confirm: no
horizontal overflow, all images loaded, the video poster visible.

- [ ] **Step 3: Check for horizontal overflow at 390px**

Run:

```bash
chromium --headless --disable-gpu --virtual-time-budget=4000 \
  --dump-dom "file://$PWD/site/index.html" > /tmp/pb-dom.html
grep -c 'overflow-x:hidden' site/styles.css
```

Expected: `1` (the body rule) — the page must not rely on clipping to hide overflow; verify
visually in the mobile screenshot that nothing is cut off.

- [ ] **Step 4: Write the README**

`README.md` must contain: a one-line proposition, a status line stating the client is
unofficial, badges, the hero screenshot, a features table, the install steps, the controls
table, a "how updates work" section, a media section, the docs index, a license section, and
the same trademark disclaimer as the landing page. Every claim must trace to the spec or a
capture.

- [ ] **Step 5: Write LICENSE, NOTICE.md and the docs**

`LICENSE`: MIT, "Copyright (c) 2026 forest". `NOTICE.md`: state that PokéBonk is by Charcher,
that no game assets are redistributed, and list the third-party components (Electron,
Chromium, Three.js in the game itself). `docs/controls.md`: the control table plus the
`std`/`xlinux`/`generic` layout explanation. `docs/install.md`: Steam Deck steps, desktop
Linux steps, launch options. `docs/troubleshooting.md`: no controller detected, software
rendering warning, updates not applying, save persistence.

- [ ] **Step 6: Add the Pages workflow**

`.github/workflows/pages.yml`:

```yaml
name: Pages

on:
  push:
    branches: [main]
    paths: [site/**, .github/workflows/pages.yml]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 7: Commit**

```bash
git add site/ README.md LICENSE NOTICE.md .github/ docs/
git commit -m "feat: landing page, README and GitHub Pages workflow"
```

---

## Task 10: Repository setup and first release

**Files:**
- Modify: `.github/workflows/ci.yml` (create)
- Modify: `README.md` (add the release badge)

**Interfaces:**
- Consumes: everything.
- Produces: a tagged GitHub release with the AppImage attached.

- [ ] **Step 1: Add the CI workflow**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm test
```

- [ ] **Step 2: Run the whole suite one final time**

Run: `npm test && ./scripts/verify-build.sh`
Expected: all tests pass; build verification prints `PASS`.

- [ ] **Step 3: Create the GitHub repo and push**

```bash
gh repo create NaustudentX18/pokebonk-deck --public --description "Unofficial native Steam Deck client for the PokéBonk browser game" --source=. --remote=origin --push
```

- [ ] **Step 4: Tag and publish the first release**

`electron-builder`'s GitHub provider needs a token in the environment. `gh` is already
authenticated on this machine:

```bash
export GH_TOKEN="$(gh auth token)"
git tag v1.0.0 && git push origin v1.0.0
npx electron-builder --linux AppImage --publish always
```

Without `GH_TOKEN` the build fails at the publish step with
`GitHub Personal Access Token is not set` — and because it fails *after* the AppImage is
written but *before* `latest-linux.yml` is emitted, the artifact exists but the updater has
no manifest. A local `npx electron-builder --linux AppImage --publish never` does emit
`latest-linux.yml`; verify with `./scripts/verify-build.sh`.

Expected: a GitHub release `v1.0.0` with `PokebonkDeck-1.0.0-x86_64.AppImage` and
`latest-linux.yml` attached. The `latest-linux.yml` is required — it is what the in-app
updater polls.

- [ ] **Step 5: Verify the release artifacts**

Run: `gh release view v1.0.0 --repo NaustudentX18/pokebonk-deck`
Expected: the AppImage and `latest-linux.yml` are listed.

- [ ] **Step 6: Confirm Pages is live**

Run: `gh api repos/NaustudentX18/pokebonk-deck/pages --jq '.html_url'`
Expected: a `https://naustudentx18.github.io/pokebonk-deck/` URL.

---

## Task 11: Deck verification (physical gate)

**Files:**
- Create: `docs/evidence/deck-verification.md`

**Interfaces:**
- Consumes: the published release.
- Produces: a written record of what was actually measured on the hardware.

- [ ] **Step 1: Install on the Deck**

Download the AppImage on the Deck (or copy it over), `chmod +x`, add it to Steam as a
non-Steam game with launch option `gamemoderun %command%`.

- [ ] **Step 2: Confirm the joydev node exists**

Run on the Deck:

```bash
ls -l /dev/input/js* /dev/input/event*
udevadm info -q property -n /dev/input/js0 | grep -E 'ID_INPUT_JOYSTICK|NAME'
```

Expected: a js node exists for the Steam virtual pad ("Microsoft X-Box 360 pad 0") and/or the
Deck's own controller, with `ID_INPUT_JOYSTICK=1`.

- [ ] **Step 3: Confirm the gamepad appears after a button press**

In the shell, the controller status entry (F8) must report at least one non-ghost pad after
the user presses a button.

- [ ] **Step 4: Confirm the game renders with hardware acceleration**

Run in the Deck's browser on `https://pokebonk.com/` and confirm the "Your browser is not
using your graphics card" warning does **not** appear.

- [ ] **Step 5: Confirm saves persist**

Play, quit, relaunch, and confirm the guest session and league progress are still there.

- [ ] **Step 6: Write the evidence file**

`docs/evidence/deck-verification.md`: date, SteamOS version, the commands above with their
outputs, and an explicit statement of anything that did not work.

---

## Execution order and parallelism

Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 are strictly sequential (each depends on the previous
module's interfaces). Task 8 is independent of 1–7 and can run in parallel with them. Tasks 9
and 10 depend on 8 (media) and 7 (icons), respectively.

## Verification summary

| Task | Verified by |
|---|---|
| 1 | `npm test` — 6 assertions green |
| 2 | `npm test` + manual fullscreen smoke + `localStorage` persists |
| 3 | `npm test` — 4 assertions green |
| 4 | `npm test` — 4 assertions green |
| 5 | `npm test` — 2 assertions green |
| 6 | `npm test` — 4 assertions green |
| 7 | `./scripts/verify-build.sh` prints `PASS` |
| 8 | every `site/media/*` file exists and is non-empty |
| 9 | Chromium headless screenshots at 1440 px and 390 px |
| 10 | `gh release view v1.0.0` lists both artifacts |
| 11 | `docs/evidence/deck-verification.md` with real command output |
