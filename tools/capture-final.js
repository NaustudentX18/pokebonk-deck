// Full-flow capture on the real GPU (hardware acceleration on), so the game's
// "not using your graphics card" warning never appears in the media.
// Throwaway tooling — not part of the shipped app.
const { app, BrowserWindow } = require('electron')
const fs = require('fs')
const path = require('path')

const OUT = process.env.CAPTURE_OUT || '/tmp/pbfinal'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const dump = (w) => w.webContents.executeJavaScript(`(() => ({
  text:(document.body?.innerText||'').replace(/\\s+/g,' ').slice(0,300),
  buttons:[...document.querySelectorAll('button,[role=button],a.btn,.btn,div.btn')]
    .map(b=>(b.innerText||b.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean).slice(0,30)
}))()`)

const click = (w, re) => w.webContents.executeJavaScript(`(() => { const want=${re};
  const all=[...document.querySelectorAll('button,[role=button],a.btn,.btn,div.btn')];
  const hit=all.find(b=>want.test((b.innerText||b.textContent||'').replace(/\\s+/g,' ').trim()));
  if(!hit) return null; hit.click(); return (hit.innerText||hit.textContent||'').replace(/\\s+/g,' ').trim(); })()`)

async function until(w, re, ms, label) {
  const t0 = Date.now()
  while (Date.now() - t0 < ms) {
    const s = await dump(w)
    if (re.test(s.text) || re.test(s.buttons.join(' '))) return s
    if (/No connection to the server/i.test(s.text)) await click(w, '/^Retry$/i')
    await sleep(2000)
  }
  console.log('[f] TIMEOUT', label)
  return dump(w)
}

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280, height: 800, show: true, frame: false, backgroundColor: '#0b0816',
    webPreferences: { backgroundThrottling: false }
  })
  await win.loadURL('https://pokebonk.com/')
  await until(win, /Play as a guest/i, 90000, 'login')
  await sleep(3500)

  const shot = async (name) => {
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await win.webContents.capturePage()).toPNG())
    console.log('[f] shot', name)
  }

  // 1) Partner select.
  await click(win, '/Play as a guest/i')
  await until(win, /I choose you/i, 90000, 'partners')
  await sleep(2500)
  await shot('02-partners')

  // 2) Pick the partner, confirm, land in the hub.
  await click(win, '/I choose you/i'); await sleep(3500)
  await click(win, '/^I choose/i'); await sleep(2500)
  await click(win, '/Yes,? I choose|Confirm/i')
  await until(win, /Play Classic/i, 120000, 'hub')
  await sleep(3500)
  for (let r = 0; r < 8; r++) { if (!await click(win, '/^Skip$/i')) break; await sleep(1200) }
  await sleep(2000)
  await shot('03-hub')

  // 3) League screen.
  await click(win, '/Play Classic/i')
  await until(win, /The League|Glossary/i, 60000, 'league')
  await sleep(4000)
  await shot('04-league')

  // 4) Start the run and capture real gameplay.
  await click(win, '/^I choose you/i'); await sleep(3000)
  await click(win, '/^I choose/i'); await sleep(2500)
  await click(win, '/Yes,? I choose|Confirm/i'); await sleep(9000)
  for (let r = 0; r < 4; r++) {
    for (const re of ['/^Got it/i', '/^Start/i', '/Confirm/i', '/^Play/i']) {
      const hit = await click(win, re)
      if (hit) { console.log('[f] click', hit); await sleep(5000) }
    }
  }
  console.log('[f] state:', JSON.stringify(await dump(win)).slice(0, 220))
  await shot('05-gameplay')

  const b64 = await win.webContents.executeJavaScript(`(async () => {
    const c = document.querySelector('canvas')
    if (!c) return 'NO_CANVAS'
    const stream = c.captureStream(30)
    const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm'
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 })
    const chunks = []
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data)
    rec.start()
    await new Promise(r => setTimeout(r, 15000))
    await new Promise(r => { rec.onstop = r; rec.stop() })
    const buf = await new Blob(chunks, { type: mime }).arrayBuffer()
    let bin = ''
    const bytes = new Uint8Array(buf)
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
    return btoa(bin)
  })()`)
  if (b64 === 'NO_CANVAS') console.log('[f] no canvas')
  else {
    fs.writeFileSync(path.join(OUT, 'gameplay.webm'), Buffer.from(b64, 'base64'))
    console.log('[f] video bytes', fs.statSync(path.join(OUT, 'gameplay.webm')).size)
  }
  await shot('06-gameplay-final')
  setTimeout(() => app.quit(), 300)
})
