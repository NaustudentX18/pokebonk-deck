'use strict'

const LEVELS = new Set(['idle', 'checking', 'available', 'downloaded', 'error', 'inactive'])

/**
 * electron-updater emits event names, not levels. Map them onto our levels
 * so the caller never has to know the difference.
 */
const STATE_ALIASES = {
  idle: 'idle',
  'update-not-available': 'idle',
  checking: 'checking',
  'checking-for-update': 'checking',
  available: 'available',
  'update-available': 'available',
  downloaded: 'downloaded',
  'update-downloaded': 'downloaded',
  error: 'error'
}

/**
 * electron-updater only works when the app runs as an AppImage — it replaces
 * the running file in place, which needs the APPIMAGE env var to know where
 * that file is.
 */
function summariseUpdaterState({ appimageEnv, state = 'idle', error = null } = {}) {
  if (!appimageEnv) {
    return {
      level: 'inactive',
      message: 'Self-update needs the AppImage build (APPIMAGE is unset).'
    }
  }
  const level = STATE_ALIASES[state] ?? (LEVELS.has(state) ? state : 'idle')
  const messages = {
    idle: 'Up to date.',
    checking: 'Checking for a client update…',
    available: 'A new client version is available.',
    downloaded: 'Update downloaded — it installs on next launch.',
    error: error ? `Update failed: ${error}` : 'Update failed.'
  }
  return { level, message: messages[level] }
}

module.exports = { summariseUpdaterState, LEVELS, STATE_ALIASES }
