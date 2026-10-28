'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { isGhostPad } = require('../src/gamepad-watcher')

test('a null slot is not a ghost', () => {
  assert.equal(isGhostPad(null), false)
})

test('a disconnected pad is not a ghost', () => {
  assert.equal(isGhostPad({ connected: false, id: 'Steam Virtual Gamepad' }), false)
})

test('a connected Steam virtual pad is a ghost', () => {
  assert.equal(isGhostPad({ connected: true, id: 'Steam Virtual Gamepad' }), true)
})

test('a connected pad whose id merely contains steam is a ghost', () => {
  assert.equal(isGhostPad({ connected: true, id: 'Steam Deck' }), true)
})

test('a connected real pad is not a ghost', () => {
  assert.equal(isGhostPad({ connected: true, id: 'Microsoft X-Box 360 pad' }), false)
})
