'use strict'

const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('path')
const fs = require('fs')

const { createGameWindow, shouldReloadWithBuildParam } = require('./window')
const { probeVersion } = require('./version-probe')
const { createUpdateService } = require('./update-service')
const { startGamepadWatcher } = require('./gamepad-watcher')
const { openMenu } = require('./menu')
const { summariseUpdaterState } = require('./shell-updater')

const log = (...args) => console.log('[deck]', ...args)

/* ------------------------------------------------------------------ *
 * Persisted state
 * ------------------------------------------------------------------ */

const stateFile = () => path.join(app.getPath('userData'), 'deck-state.json')

function readState() {
  try {
    return JSON.parse(fs.readFileSync(stateFile(), 'utf8'))
  } catch {
    return {}
  }
}

function writeState(patch) {
  try {
    const next = { ...readState(), ...patch }
    fs.writeFileSync(stateFile(), JSON.stringify(next, null, 2))
  } catch {
    /* A read-only userData dir must not break the app. */
  }
}

const getLastBuild = () => readState().lastBuild ?? null
const setLastBuild = (build) => writeState({ lastBuild: build })

/* ------------------------------------------------------------------ *
 * GPU fallback
 * ------------------------------------------------------------------ *
 * Chromium aborts the whole app when the GPU process cannot start (a VM, a
 * remote desktop, a missing /dev/dri). The game still runs on software
 * rendering, so fall back to that once and remember the choice.
 */

const SOFTWARE_FLAG = 'softwareRendering'

function useSoftwareRendering() {
  try {
    if (process.argv.includes('--force-gpu') || process.argv.includes('--reset-gpu')) {
      // Clear a previously persisted fallback: the GPU works, so use it.
      writeState({ [SOFTWARE_FLAG]: false })
      return false
    }
    // A relaunch after a GPU death asks for software rendering for THIS run
    // only. Persisting it would leave the game crawling on SwiftShader for
    // ever, which looks exactly like "it never finishes loading".
    if (process.argv.includes('--software-rendering')) return true
    return Boolean(readState()[SOFTWARE_FLAG])
  } catch {
    return false
  }
}

// Must be applied before the app becomes ready. Electron's own API is what
// actually stops Chromium from requiring a GPU process; the switches alone
// still leave it spawning one and aborting the app.
if (useSoftwareRendering()) {
  app.disableHardwareAcceleration()
  app.commandLine.appendSwitch('use-gl', 'angle')
  app.commandLine.appendSwitch('use-angle', 'swiftshader')
  app.commandLine.appendSwitch('enable-unsafe-swiftshader')
  log('software rendering enabled (persisted from a previous GPU failure)')
}

app.on('child-process-gone', (_event, details) => {
  if (details.type !== 'GPU') return
  if (useSoftwareRendering()) return
  log('GPU process died — relaunching with software rendering for this run')
  app.relaunch(['--software-rendering'])
  app.exit(0)
})

/* ------------------------------------------------------------------ *
 * Update handling
 * ------------------------------------------------------------------ */

/**
 * Reload the game onto a new upstream build.
 *
 * Mirrors the game's own teardown (bF() in its bundle): stop the animation
 * loop, dispose the renderer, force the WebGL context to be released, then
 * navigate — so the new build starts from a clean context instead of a
 * disposed one.
 */
function reloadForBuild(win, build) {
  const target = shouldReloadWithBuildParam(win.webContents.getURL(), build)
  log('upstream build changed ->', build, '| reloading', target)
  win.webContents
    .executeJavaScript(`(() => {
      try {
        const c = document.querySelector('canvas')
        if (c) {
          const gl = c.getContext('webgl2') || c.getContext('webgl')
          if (gl) {
            const lose = gl.getExtension('WEBGL_lose_context')
            if (lose) lose.loseContext()
          }
        }
      } catch {}
    })()`)
    .catch(() => {})
    .finally(() => {
      win.loadURL(target).catch(() => win.webContents.reloadIgnoringCache())
    })
}

/* ------------------------------------------------------------------ *
 * Shell shortcuts
 * ------------------------------------------------------------------ */

function registerShortcuts(win) {
  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return

    const key = input.key.toLowerCase()
    const ctrl = input.control || input.meta

    if (key === 'f10') {
      event.preventDefault()
      openMenu(win, { onCommand: (id) => handleCommand(win, id) })
      return
    }
    if (key === 'f11') {
      event.preventDefault()
      win.setFullScreen(!win.isFullScreen())
      return
    }
    if (key === 'f5') {
      event.preventDefault()
      win.webContents.reloadIgnoringCache()
      return
    }
    if (key === 'f8') {
      event.preventDefault()
      reportGamepads(win)
      return
    }
    if (ctrl && key === 'q') {
      event.preventDefault()
      app.quit()
    }
    // Escape is deliberately NOT intercepted: the game uses it to release
    // the pointer lock.
  })
}

function reportGamepads(win) {
  win.webContents
    .executeJavaScript(`(() => {
      const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : []
      return JSON.stringify(pads.map(p => ({ id: p.id, index: p.index, mapping: p.mapping })))
    })()`)
    .then((json) => log('gamepads:', json))
    .catch(() => log('gamepads: unavailable'))
}

function handleCommand(win, id) {
  switch (id) {
    case 'reload':
      win.webContents.reloadIgnoringCache()
      break
    case 'fullscreen':
      win.setFullScreen(!win.isFullScreen())
      break
    case 'gamepad-status':
      reportGamepads(win)
      break
    case 'quit':
      app.quit()
      break
    default:
      break
  }
}

/* ------------------------------------------------------------------ *
 * Shell self-update (AppImage channel)
 * ------------------------------------------------------------------ */

function startShellUpdater(win) {
  let autoUpdater = null
  try {
    ({ autoUpdater } = require('electron-updater'))
  } catch (err) {
    log('self-update unavailable:', err.message)
    return
  }

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  const report = (state, error = null) => {
    const { level, message } = summariseUpdaterState({
      appimageEnv: process.env.APPIMAGE,
      state,
      error
    })
    log(`updater[${level}]:`, message)
    win.webContents.send('deck:client-update', { level, message })
  }

  autoUpdater.on('checking-for-update', () => report('checking'))
  autoUpdater.on('update-available', () => report('available'))
  autoUpdater.on('update-not-available', () => report('idle'))
  autoUpdater.on('update-downloaded', () => report('downloaded'))
  autoUpdater.on('error', (err) => report('error', err?.message ?? String(err)))

  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((err) => report('error', err.message))
  }, 5000)
}

/* ------------------------------------------------------------------ *
 * Boot
 * ------------------------------------------------------------------ */

/**
 * --selftest: load the game, report what this machine actually provides, exit.
 * Used by tools/deck-verify.sh to prove the client works on real hardware.
 */
async function runSelfTest() {
  const out = { ok: false, checks: {} }
  const win = createGameWindow()

  try {
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('the game did not load in 60s')), 60000)
      win.webContents.once('did-finish-load', () => { clearTimeout(timer); resolve() })
      win.webContents.once('did-fail-load', (_e, code, desc) => {
        clearTimeout(timer); reject(new Error(`load failed: ${code} ${desc}`))
      })
    })
    out.checks.loaded = true
  } catch (error) {
    out.checks.loadError = String(error.message || error)
  }

  // Give the game a moment to build its canvas and start its own checks.
  await new Promise((r) => setTimeout(r, 6000))

  try {
    const info = await win.webContents.executeJavaScript(`(() => {
      const canvas = document.querySelector('canvas')
      const gl = canvas && (canvas.getContext('webgl2') || canvas.getContext('webgl'))
      const dbg = gl && gl.getExtension('WEBGL_debug_renderer_info')
      const pads = navigator.getGamepads ? [...navigator.getGamepads()].filter(Boolean) : []
      return JSON.stringify({
        origin: location.origin,
        build: document.querySelector('meta[name="pokebonk-build"]')?.content || null,
        title: document.title,
        canvas: document.querySelectorAll('canvas').length,
        webgl2: !!canvas && !!canvas.getContext('webgl2'),
        renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
        softwareRenderer: dbg ? /swiftshader|llvmpipe|softpipe|software|basic render/i
          .test(String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL))) : null,
        gamepads: pads.map(p => ({ id: p.id, index: p.index, mapping: p.mapping })),
        bridge: typeof window.__deck
      })
    })()`)
    Object.assign(out.checks, JSON.parse(info))
  } catch (error) {
    out.checks.probeError = String(error.message || error)
  }

  // The window's own state: on the Deck this is what decides whether the
  // game is actually visible, not whether the page rendered.
  try {
    const bounds = win.getBounds()
    out.checks.window = {
      visible: win.isVisible(),
      focused: win.isFocused(),
      fullScreen: win.isFullScreen(),
      bounds: `${bounds.width}x${bounds.height}+${bounds.x}+${bounds.y}`,
      windows: BrowserWindow.getAllWindows().length
    }
  } catch (error) {
    out.checks.window = { error: String(error.message || error) }
  }

  // Optional: capture what the app is showing.
  const shotIndex = process.argv.indexOf('--screenshot')
  if (shotIndex > -1 && process.argv[shotIndex + 1]) {
    try {
      const target = process.argv[shotIndex + 1]
      fs.writeFileSync(target, (await win.webContents.capturePage()).toPNG())
      out.checks.screenshot = target
    } catch (error) {
      out.checks.screenshot = `failed: ${error.message || error}`
    }
  }

  out.checks.electron = process.versions.electron
  out.checks.chrome = process.versions.chrome
  out.checks.upstream = await probeVersion()
  out.ok = Boolean(out.checks.loaded) && out.checks.webgl2 === true
  console.log('SELFTEST_JSON ' + JSON.stringify(out))
  app.exit(out.ok ? 0 : 1)
}

app.whenReady().then(() => {
  if (process.argv.includes('--selftest')) {
    void runSelfTest()
    return
  }

  const win = createGameWindow()
  registerShortcuts(win)

  const updates = createUpdateService({
    probe: () => probeVersion(),
    getLastBuild,
    setLastBuild,
    onUpdate: ({ build, version }) => {
      log(`upstream game updated: ${version} (${build})`)
      reloadForBuild(win, build)
    }
  })

  win.webContents.on('did-finish-load', () => {
    void updates.checkNow()
  })

  // Auto-retry initial load when waking from sleep or connecting to WiFi
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    if ([-106, -105, -21, -2].includes(errorCode)) {
      log(`network not ready (${errorCode}: ${errorDescription}) — retrying in 4s…`)
      setTimeout(() => {
        if (!win.isDestroyed()) {
          win.loadURL(validatedURL || 'https://pokebonk.com/').catch(() => {})
        }
      }, 4000)
    }
  })
  updates.start(30 * 60 * 1000)

  const stopWatcher = startGamepadWatcher(win.webContents, {
    onPad: (pads) => {
      log(pads.length > 0 ? `gamepad: ${pads.map((p) => p.id).join(', ')}` : 'gamepad: none')
    }
  })

  ipcMain.on('deck:reload', () => win.webContents.reloadIgnoringCache())
  ipcMain.on('deck:quit', () => app.quit())
  ipcMain.on('deck:open-menu', () => openMenu(win, { onCommand: (id) => handleCommand(win, id) }))
  ipcMain.on('deck:gamepad', (_e, info) => log('page reported gamepad:', JSON.stringify(info)))
  ipcMain.handle('deck:version', () => ({
    app: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
    lastBuild: getLastBuild()
  }))

  startShellUpdater(win)

  app.on('will-quit', () => {
    stopWatcher()
    updates.stop()
  })

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createGameWindow()
  })
})

app.on('window-all-closed', () => app.quit())
