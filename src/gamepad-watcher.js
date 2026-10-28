'use strict'

const POLL_INTERVAL_MS = 250

/**
 * Steam exposes a virtual Xbox-360 pad alongside (or instead of) the Deck's
 * own controller. The virtual one must not be surfaced to the game, or the
 * game sees two pads with the same buttons.
 */
function isGhostPad(pad) {
  if (!pad || !pad.connected) return false
  const id = String(pad.id ?? '')
  return /virtual|steam/i.test(id)
}

/**
 * Poll for gamepads.
 *
 * Chromium deliberately reports nothing until the user has interacted with a
 * controller (gamepad_service.cc: did_observe_user_gesture), so relying on
 * the `gamepadconnected` event alone would miss the pad. Polling also picks
 * up a pad that was already connected before the app started.
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
