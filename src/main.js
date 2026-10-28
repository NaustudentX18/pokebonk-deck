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

app.whenReady().then(() => {
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
