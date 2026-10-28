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

/**
 * The shell overlay: a small frameless window on top of the game.
 * It talks back to the main process through the console-message channel,
 * which keeps the overlay free of any node integration.
 */
function openMenu(parentWindow, { onCommand } = {}) {
  const menu = new BrowserWindow({
    width: 460,
    height: 340,
    parent: parentWindow,
    show: false,
    frame: false,
    transparent: true,
    resizable: false,
    skipTaskbar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false }
  })

  menu.loadFile(path.join(__dirname, 'menu.html'))
  menu.once('ready-to-show', () => menu.show())

  menu.webContents.on('console-message', (_event, level, message) => {
    // Electron 45 changed this signature; handle both shapes.
    const text = typeof message === 'string' ? message : String(message?.message ?? '')
    if (!text.startsWith('deck-command:')) return
    onCommand?.(text.slice('deck-command:'.length))
    menu.close()
  })

  return menu
}

module.exports = { MENU_ITEMS, openMenu }
