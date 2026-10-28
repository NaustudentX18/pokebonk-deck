'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { SHORTCUT_BUTTON_MAP, createShortcutHandler } = require('../src/pad-shortcuts')

test('SHORTCUT_BUTTON_MAP maps index 8 to Big Map (M)', () => {
  assert.equal(SHORTCUT_BUTTON_MAP[8].key, 'm')
  assert.equal(SHORTCUT_BUTTON_MAP[8].code, 'KeyM')
})

test('SHORTCUT_BUTTON_MAP maps index 10 to Auto-run (T)', () => {
  assert.equal(SHORTCUT_BUTTON_MAP[10].key, 't')
  assert.equal(SHORTCUT_BUTTON_MAP[10].code, 'KeyT')
})

test('SHORTCUT_BUTTON_MAP maps index 11 to Auto-ultimate (Y)', () => {
  assert.equal(SHORTCUT_BUTTON_MAP[11].key, 'y')
  assert.equal(SHORTCUT_BUTTON_MAP[11].code, 'KeyY')
})

test('createShortcutHandler triggers dispatch on button press', () => {
  const dispatched = []
  const handler = createShortcutHandler((key, code, keyCode) => {
    dispatched.push({ key, code, keyCode })
  })

  const buttons = Array.from({ length: 16 }, () => ({ pressed: false }))
  buttons[8] = { pressed: true } // Select / Back

  const result = handler({ buttons })
  assert.deepEqual(result, ['Big Map'])
  assert.equal(dispatched.length, 1)
  assert.deepEqual(dispatched[0], { key: 'm', code: 'KeyM', keyCode: 77 })
})

test('createShortcutHandler does not re-trigger while button is held down', () => {
  const dispatched = []
  const handler = createShortcutHandler((key, code) => dispatched.push({ key, code }))

  const buttons = Array.from({ length: 16 }, () => ({ pressed: false }))
  buttons[10] = { pressed: true } // L3

  handler({ buttons })
  assert.equal(dispatched.length, 1)

  // Next frame, still held down
  const result2 = handler({ buttons })
  assert.deepEqual(result2, [])
  assert.equal(dispatched.length, 1)
})

test('createShortcutHandler re-triggers after release and press', () => {
  const dispatched = []
  const handler = createShortcutHandler((key, code) => dispatched.push({ key, code }))

  const pressed = Array.from({ length: 16 }, () => ({ pressed: false }))
  pressed[11] = { pressed: true } // R3

  const released = Array.from({ length: 16 }, () => ({ pressed: false }))

  handler({ buttons: pressed })
  assert.equal(dispatched.length, 1)

  handler({ buttons: released })
  assert.equal(dispatched.length, 1)

  handler({ buttons: pressed })
  assert.equal(dispatched.length, 2)
})

// The preload runs SANDBOXED, and a sandboxed preload cannot require a
// relative file — a relative require throws and takes the whole preload
// down (which silently removes the __deck bridge as well). So the mapping is
// inlined into src/preload.js, and this test makes sure the inline copy
// cannot drift away from the module.
const fs = require('node:fs')
const path = require('node:path')

test('the preload carries the same mapping as the module', () => {
  const preload = fs.readFileSync(path.join(__dirname, '..', 'src', 'preload.js'), 'utf8')
  for (const [index, shortcut] of Object.entries(SHORTCUT_BUTTON_MAP)) {
    assert.ok(
      preload.includes(`${index}: { key: '${shortcut.key}', code: '${shortcut.code}', keyCode: ${shortcut.keyCode}`),
      `the preload is missing button ${index} (${shortcut.name}) — it must match src/pad-shortcuts.js`
    )
  }
})

test('the preload does not require a relative module', () => {
  const preload = fs.readFileSync(path.join(__dirname, '..', 'src', 'preload.js'), 'utf8')
  const relativeRequire = preload.match(/require\(\s*['"]\.[^'"]+['"]\s*\)/)
  assert.equal(relativeRequire, null,
    'a sandboxed preload cannot require a relative file — inline the code instead')
})
