'use strict'

/**
 * Maps Steam Deck / controller buttons to the browser game's keyboard-only shortcuts:
 *   Button 8  (Select / View / Back)     -> 'm' / 'KeyM' (Big map)
 *   Button 10 (L3 / Left Stick Click)    -> 't' / 'KeyT' (Auto-run toggle)
 *   Button 11 (R3 / Right Stick Click)   -> 'y' / 'KeyY' (Auto-ultimate toggle)
 */
const SHORTCUT_BUTTON_MAP = {
  8: { key: 'm', code: 'KeyM', keyCode: 77, name: 'Big Map' },
  10: { key: 't', code: 'KeyT', keyCode: 84, name: 'Auto-run' },
  11: { key: 'y', code: 'KeyY', keyCode: 89, name: 'Auto Ultimate' }
}

function createShortcutHandler(dispatchKey) {
  const previousState = {}

  return function processGamepad(pad) {
    if (!pad || !pad.buttons) return []
    const triggered = []

    for (const [btnIndexStr, shortcut] of Object.entries(SHORTCUT_BUTTON_MAP)) {
      const idx = Number(btnIndexStr)
      const btn = pad.buttons[idx]
      const isPressed = typeof btn === 'object' && btn !== null ? Boolean(btn.pressed) : Boolean(btn)
      const wasPressed = Boolean(previousState[idx])

      if (isPressed && !wasPressed) {
        dispatchKey(shortcut.key, shortcut.code, shortcut.keyCode)
        triggered.push(shortcut.name)
      }
      previousState[idx] = isPressed
    }

    return triggered
  }
}

module.exports = { SHORTCUT_BUTTON_MAP, createShortcutHandler }
