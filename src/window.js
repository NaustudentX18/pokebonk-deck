'use strict'

const { BrowserWindow, session } = require('electron')
const path = require('path')

/**
 * The game is loaded as a TOP-LEVEL document, never in an iframe:
 * pokebonk.com sends `Content-Security-Policy: frame-ancestors 'self'` and
 * `X-Frame-Options: SAMEORIGIN`, so cross-origin framing is blocked.
 */
const GAME_URL = 'https://pokebonk.com/'

/**
 * Build the reload URL for a new upstream build.
 * The game itself navigates to `?v=<build>` after tearing its renderer down.
 */
function shouldReloadWithBuildParam(currentUrl, build) {
  const url = new URL(currentUrl)
  url.searchParams.set('v', build)
  return url.toString()
}

function createGameWindow() {
  // A persistent partition: the game's localStorage lives on the
  // https://pokebonk.com origin (pb.session, pb.guest, pb.device) and must
  // survive restarts or the player loses their session.
  const persist = session.fromPartition('persist:pokebonk-deck')

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    fullscreen: true,
    kiosk: true,
    backgroundColor: '#1a1630',
    autoHideMenuBar: true,
    title: 'PokéBonk Deck',
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
