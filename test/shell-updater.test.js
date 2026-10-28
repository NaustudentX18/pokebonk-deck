'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { summariseUpdaterState } = require('../src/shell-updater')

test('no AppImage env means the updater is inactive', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: null }).level, 'inactive')
})

test('an AppImage env means the updater is active', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/home/x/App.AppImage' }).level, 'idle')
})

test('a downloaded update reports its level', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/x', state: 'update-downloaded' }).level, 'downloaded')
})

test('an error reports the error level', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/x', state: 'error' }).level, 'error')
})

test('an unknown state falls back to idle', () => {
  assert.equal(summariseUpdaterState({ appimageEnv: '/x', state: 'nonsense' }).level, 'idle')
})

test('the error message carries the reason', () => {
  const { message } = summariseUpdaterState({ appimageEnv: '/x', state: 'error', error: '404' })
  assert.match(message, /404/)
})
