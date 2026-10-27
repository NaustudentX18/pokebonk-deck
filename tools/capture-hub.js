// Clean hub capture on the real GPU (hardware accel on) so the game does not
// show its software-rendering warning. Throwaway tooling.
const { app, BrowserWindow } = require('electron')
const fs = require('fs'); const path = require('path')
const OUT = process.env.CAPTURE_OUT || '/tmp/pbhub'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise(r => setTimeout(r, ms))
const dump = (w) => w.webContents.executeJavaScript(`(() => ({
  text:(document.body?.innerText||'').replace(/\\s+/g,' ').slice(0,300),
  buttons:[...document.querySelectorAll('button,[role=button],a.btn,.btn,div.btn')].map(b=>(b.innerText||b.textContent||'').replace(/\\s+/g,' ').trim()).filter(Boolean).slice(0,30)
}))()`)
const click = (w, re) => w.webContents.executeJavaScript(`(() => { const want=${re};
  const all=[...document.querySelectorAll('button,[role=button],a.btn,.btn,div.btn')];
  const hit=all.find(b=>want.test((b.innerText||b.textContent||'').replace(/\\s+/g,' ').trim()));
  if(!hit) return null; hit.click(); return (hit.innerText||hit.textContent||'').trim(); })()`)
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 1280, height: 800, show: true, frame: false, backgroundColor: '#0b0816' })
  await win.loadURL('https://pokebonk.com/')
  for (let i=0;i<90;i++){ if((await dump(win)).buttons.length) break; await sleep(1000) }
  await sleep(5000)
  const gpu = await win.webContents.executeJavaScript(`(() => { const gl=document.createElement('canvas').getContext('webgl2');
    const d=gl&&gl.getExtension('WEBGL_debug_renderer_info'); return d?gl.getParameter(d.UNMASKED_RENDERER_WEBGL):null })()`)
  console.log('[h] renderer:', gpu)
  await click(win, '/Play as a guest/i')
  for (let i=0;i<40;i++){ if(/I choose you/i.test((await dump(win)).text)) break; await sleep(2000) }
  await click(win, '/I choose you/i'); await sleep(3500)
  await click(win, '/^I choose/i'); await sleep(2500)
  await click(win, '/Yes,? I choose|Confirm/i')
  for (let i=0;i<40;i++){ if(/Play Classic/i.test((await dump(win)).text)) break; await sleep(2000) }
  await sleep(4000)
  // Dismiss the 6-step tutorial so the hub screenshot is clean.
  for (let r = 0; r < 8; r++) {
    const hit = await click(win, '/^Skip$/i')
    if (!hit) break
    await sleep(1500)
  }
  await sleep(2500)
  console.log('[h] hub?', (await dump(win)).buttons.slice(0,10).join(' | '))
  fs.writeFileSync(path.join(OUT,'03-hub.png'), (await win.webContents.capturePage()).toPNG())
  console.log('[h] shot 03-hub')
  // League screen
  await click(win, '/Play Classic/i'); await sleep(9000)
  await click(win, '/^Got it/i'); await sleep(3000)
  fs.writeFileSync(path.join(OUT,'04-league.png'), (await win.webContents.capturePage()).toPNG())
  console.log('[h] shot 04-league')
  await sleep(1000)
  setTimeout(() => app.quit(), 300)
})
