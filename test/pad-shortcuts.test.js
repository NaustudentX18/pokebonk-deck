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
