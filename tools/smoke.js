// Smoke test: boot the real app against the live game, prove the origin
// storage persists, and exercise the shell's own reload path.
// Throwaway tooling — not part of the shipped app.
const { app, BrowserWindow } = require('electron')
const path = require('path')
const fs = require('fs')

const OUT = '/tmp/pbsmoke'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

app.commandLine.appendSwitch('use-gl', 'angle')
app.commandLine.appendSwitch('use-angle', 'swiftshader')
app.commandLine.appendSwitch('enable-unsafe-swiftshader')
app.disableHardwareAcceleration()

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: true,
    frame: false,
    backgroundColor: '#1a1630',
    webPreferences: {
      partition: 'persist:pokebonk-deck',
      preload: path.join(__dirname, '..', 'src', 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  await win.loadURL('https://pokebonk.com/')
  console.log('[smoke] loaded')

  for (let i = 0; i < 60; i++) {
    const ready = await win.webContents.executeJavaScript(
      `document.querySelectorAll('canvas').length > 0`
    )
    if (ready) break
    await sleep(1000)
  }
  await sleep(5000)

  const probe = await win.webContents.executeJavaScript(`(() => {
    const ls = []
    for (let i = 0; i < localStorage.length; i++) ls.push(localStorage.key(i))
    return JSON.stringify({
      origin: location.origin,
      build: document.querySelector('meta[name="pokebonk-build"]')?.content || null,
      title: document.title,
      canvas: document.querySelectorAll('canvas').length,
      localStorageKeys: ls,
      bridge: typeof window.__deck,
      device: ls.includes('pb.device') ? 'present' : 'absent'
    })
  })()`)
  console.log('[smoke] probe', probe)

  // The bridge the preload exposes must be visible to the page.
  const bridge = await win.webContents.executeJavaScript(
    `JSON.stringify({ deck: typeof window.__deck, keys: window.__deck ? Object.keys(window.__deck) : [] })`
  )
  console.log('[smoke] bridge', bridge)

  // The shell's own version probe (out-of-process fetch).
  const { probeVersion } = require(path.join(__dirname, '..', 'src', 'version-probe'))
  console.log('[smoke] probeVersion', JSON.stringify(await probeVersion()))

  // The gamepad poll must not throw even with no controller attached.
  const { startGamepadWatcher } = require(path.join(__dirname, '..', 'src', 'gamepad-watcher'))
  const stop = startGamepadWatcher(win.webContents, {
    onPad: (pads) => console.log('[smoke] pads', JSON.stringify(pads))
  })
  await sleep(1500)
  stop()

  fs.writeFileSync(path.join(OUT, 'probe.json'), probe)
  setTimeout(() => app.quit(), 300)
})
