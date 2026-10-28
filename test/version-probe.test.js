'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { checkBuild, probeVersion } = require('../src/version-probe')

test('checkBuild reports a change when the build id differs', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: 'mvdmwnj4' }), {
    changed: true,
    next: 'mvpt1dlr'
  })
})

test('checkBuild reports no change for the same build id', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: 'mvpt1dlr' }), {
    changed: false,
    next: 'mvpt1dlr'
  })
})

test('checkBuild reports a change when there is no previous build', () => {
  assert.deepEqual(checkBuild({ current: 'mvpt1dlr', previous: null }), {
    changed: true,
    next: 'mvpt1dlr'
  })
})

test('probeVersion reads build and version from version.json', async () => {
  const fetchImpl = async () => ({
    ok: true,
    json: async () => ({ build: 'mvpt1dlr', version: '0.8.59' })
  })
  assert.deepEqual(await probeVersion(fetchImpl), { build: 'mvpt1dlr', version: '0.8.59' })
})

test('probeVersion returns null when the endpoint fails', async () => {
  const fetchImpl = async () => { throw new Error('network down') }
  assert.equal(await probeVersion(fetchImpl), null)
})

test('probeVersion returns null when the payload has no build id', async () => {
  const fetchImpl = async () => ({ ok: true, json: async () => ({ version: '0.8.59' }) })
  assert.equal(await probeVersion(fetchImpl), null)
})

test('probeVersion returns null on a non-ok response', async () => {
  const fetchImpl = async () => ({ ok: false, status: 500, json: async () => ({}) })
  assert.equal(await probeVersion(fetchImpl), null)
})
