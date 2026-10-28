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
