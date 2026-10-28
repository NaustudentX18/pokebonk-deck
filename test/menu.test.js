'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { MENU_ITEMS } = require('../src/menu')

test('the menu offers the console-standard actions', () => {
  const ids = MENU_ITEMS.map((i) => i.id)
  for (const expected of ['resume', 'fullscreen', 'reload', 'gamepad-status', 'quit']) {
    assert.ok(ids.includes(expected), `missing menu item: ${expected}`)
  }
})

test('every menu item has a label and a shortcut', () => {
  for (const item of MENU_ITEMS) {
    assert.equal(typeof item.label, 'string')
    assert.equal(typeof item.shortcut, 'string')
  }
})

test('menu item ids are unique', () => {
  const ids = MENU_ITEMS.map((i) => i.id)
  assert.equal(new Set(ids).size, ids.length)
})
