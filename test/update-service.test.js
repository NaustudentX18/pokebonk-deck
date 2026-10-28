'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { createUpdateService } = require('../src/update-service')

function makeService(probeResults, initialBuild = 'mvpt1dlr') {
  const seen = []
  let last = initialBuild
  const svc = createUpdateService({
    probe: async () => probeResults.shift() ?? null,
    getLastBuild: () => last,
    setLastBuild: (b) => { last = b },
    onUpdate: (info) => seen.push(info)
  })
  return { svc, seen }
}

test('a changed upstream build triggers onUpdate', async () => {
  const { svc, seen } = makeService([{ build: 'mvob1c8t', version: '0.9.0' }])
  await svc.checkNow()
  assert.deepEqual(seen, [{ build: 'mvob1c8t', version: '0.9.0' }])
})

test('the same build does not trigger onUpdate twice', async () => {
  const { svc, seen } = makeService([
    { build: 'mvpt1dlr', version: '0.8.59' },
    { build: 'mvpt1dlr', version: '0.8.59' }
  ])
  await svc.checkNow()
  await svc.checkNow()
  assert.equal(seen.length, 0)
})

test('a failed probe does not trigger onUpdate and does not throw', async () => {
  const { svc, seen } = makeService([null])
  await svc.checkNow()
  assert.equal(seen.length, 0)
})

test('the last build is stored after a successful probe', async () => {
  let stored = null
  const svc = createUpdateService({
    probe: async () => ({ build: 'mvob1c8t', version: '0.9.0' }),
    getLastBuild: () => stored,
    setLastBuild: (b) => { stored = b },
    onUpdate: () => {}
  })
  await svc.checkNow()
  assert.equal(stored, 'mvob1c8t')
})

test('a first run with no stored build is a baseline, not an update', async () => {
  const { svc, seen } = makeService([{ build: 'mvpt1dlr', version: '0.8.59' }], null)
  await svc.checkNow()
  assert.equal(seen.length, 0)
})
