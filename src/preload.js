'use strict'

const { contextBridge, ipcRenderer } = require('electron')

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
 * Gamepad Shortcut Bridge for Steam Deck & Controllers.
 *
 * Maps buttons the game does not use to the browser's keyboard-only
 * shortcuts:
 *   Button 8  (Select / View / Back)   -> 'm' (Big map)
 *   Button 10 (Left stick click / L3)   -> 't' (Auto-run)
 *   Button 11 (Right stick click / R3)  -> 'y' (Auto-ultimate)
 *
 * The mapping is inlined rather than required from another file: this preload
 * runs SANDBOXED, and a sandboxed preload can only require Electron's own
 * modules — a relative require throws and takes the whole preload down with
 * it, which silently removes the bridge above as well.
 */

const SHORTCUT_BUTTON_MAP = {
  8: { key: 'm', code: 'KeyM', keyCode: 77, name: 'Big Map' },
  10: { key: 't', code: 'KeyT', keyCode: 84, name: 'Auto-run' },
  11: { key: 'y', code: 'KeyY', keyCode: 89, name: 'Auto Ultimate' }
}

const previousState = {}

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

function processGamepad(pad) {
  if (!pad || !pad.buttons) return
  for (const [btnIndexStr, shortcut] of Object.entries(SHORTCUT_BUTTON_MAP)) {
    const idx = Number(btnIndexStr)
    const btn = pad.buttons[idx]
    const isPressed = typeof btn === 'object' && btn !== null ? Boolean(btn.pressed) : Boolean(btn)
    const wasPressed = Boolean(previousState[idx])
    if (isPressed && !wasPressed) dispatchKey(shortcut.key, shortcut.code, shortcut.keyCode)
    previousState[idx] = isPressed
  }
}

function pollGamepads() {
  const pads = typeof navigator.getGamepads === 'function' ? navigator.getGamepads() : []
  for (const pad of pads) {
    if (pad && pad.connected) {
      processGamepad(pad)
      break
    }
  }
}

// A timer, not requestAnimationFrame: rAF is throttled to a stop when the
// window is not the focused/visible one, and the bridge would silently stop
// working — which is exactly what happens when the shell is behind another
// window, or in the moment before the game takes focus.
if (typeof window !== 'undefined') {
  setInterval(pollGamepads, 100)
}
