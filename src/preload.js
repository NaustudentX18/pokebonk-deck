'use strict'

const { contextBridge, ipcRenderer } = require('electron')
const { createShortcutHandler } = require('./pad-shortcuts')

/**
 * The bridge the game page can use to talk to the shell.
 * The game itself does not use it — the shell's own overlay and shortcuts
 * drive everything. It exists so the page can ask for a clean reload after
 * an upstream build change instead of leaving a disposed WebGL context behind.
 */
contextBridge.exposeInMainWorld('__deck', {
  reload: () => ipcRenderer.send('deck:reload'),
  quit: () => ipcRenderer.send('deck:quit'),
  openMenu: () => ipcRenderer.send('deck:open-menu'),
  reportGamepad: (info) => ipcRenderer.send('deck:gamepad', info),
  version: () => ipcRenderer.invoke('deck:version')
})

/**
 * Gamepad Shortcut Bridge for Steam Deck & Controllers:
 * Maps unmapped physical buttons to browser keyboard actions:
 *   Button 8  (Select / View / Back)     -> 'm' (Big Map)
 *   Button 10 (Left Stick Click / L3)    -> 't' (Auto-Run)
 *   Button 11 (Right Stick Click / R3)   -> 'y' (Auto-Ultimate)
 */
function dispatchKey(key, code, keyCode) {
  const down = new KeyboardEvent('keydown', {
    key,
    code,
    keyCode,
    which: keyCode,
    bubbles: true,
    cancelable: true
  })
  const up = new KeyboardEvent('keyup', {
    key,
    code,
    keyCode,
    which: keyCode,
    bubbles: true,
    cancelable: true
  })

  window.dispatchEvent(down)
  document.dispatchEvent(down)
  setTimeout(() => {
    window.dispatchEvent(up)
    document.dispatchEvent(up)
  }, 80)
}

const processGamepad = createShortcutHandler(dispatchKey)

function pollGamepads() {
  const pads = typeof navigator.getGamepads === 'function' ? navigator.getGamepads() : []
  for (const pad of pads) {
    if (pad && pad.connected) {
      processGamepad(pad)
      break
    }
  }
  requestAnimationFrame(pollGamepads)
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    requestAnimationFrame(pollGamepads)
  })
}
