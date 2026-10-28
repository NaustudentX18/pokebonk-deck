'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { GAME_URL, shouldReloadWithBuildParam } = require('../src/window')

test('the game is loaded as a top-level document, not framed', () => {
  assert.equal(GAME_URL, 'https://pokebonk.com/')
})

test('a build change produces a ?v= reload url', () => {
  assert.equal(
    shouldReloadWithBuildParam('https://pokebonk.com/', 'mvpt1dlr'),
    'https://pokebonk.com/?v=mvpt1dlr'
  )
})

test('the reload url preserves an existing query string', () => {
  assert.equal(
    shouldReloadWithBuildParam('https://pokebonk.com/?lang=en', 'mvpt1dlr'),
    'https://pokebonk.com/?lang=en&v=mvpt1dlr'
  )
})

test('the reload url replaces a stale v parameter', () => {
  assert.equal(
    shouldReloadWithBuildParam('https://pokebonk.com/?v=oldbuild', 'mvpt1dlr'),
    'https://pokebonk.com/?v=mvpt1dlr'
  )
})
