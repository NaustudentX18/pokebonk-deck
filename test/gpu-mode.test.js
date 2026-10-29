'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const {
  SOFTWARE_RENDERER,
  HARDWARE_GPU_FLAGS,
  isSoftwareRenderer,
  shouldEscalate
} = require('../src/gpu-mode')

test('the Steam Deck hardware renderer is not software', () => {
  const deck = 'ANGLE (AMD, AMD Custom GPU 0932 (radeonsi vangogh ACO), OpenGL 4.6)'
  assert.equal(isSoftwareRenderer(deck), false)
})

test('SwiftShader is recognised as software', () => {
  const sw = 'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)'
  assert.equal(isSoftwareRenderer(sw), true)
})

test('llvmpipe is recognised as software', () => {
  assert.equal(isSoftwareRenderer('llvmpipe (LLVM 15.0.7, 256 bits)'), true)
})

test('the pattern matches the game\'s own', () => {
  // The game's bundle has: /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i
  assert.equal(SOFTWARE_RENDERER.source,
    'swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic')
})

test('an unknown renderer is not treated as software', () => {
  assert.equal(isSoftwareRenderer('Mesa/X.org'), false)
  assert.equal(isSoftwareRenderer(''), false)
  assert.equal(isSoftwareRenderer(undefined), false)
})

test('a software renderer escalates once', () => {
  assert.equal(shouldEscalate({ renderer: 'llvmpipe', tried: false }), true)
})

test('a software renderer does not escalate twice', () => {
  assert.equal(shouldEscalate({ renderer: 'llvmpipe', tried: true }), false)
})

test('a hardware renderer never escalates', () => {
  assert.equal(shouldEscalate({
    renderer: 'ANGLE (AMD, AMD Custom GPU 0932 (radeonsi vangogh ACO), OpenGL 4.6)',
    tried: false
  }), false)
})

test('the escalation flags ask for the real GPU', () => {
  assert.ok(HARDWARE_GPU_FLAGS.includes('--ignore-gpu-blocklist'))
  assert.ok(HARDWARE_GPU_FLAGS.includes('--ozone-platform=x11'))
})

test('the escalation flags keep WebGL2 alive', () => {
  // Measured: --use-gl=desktop turns WebGL2 off entirely on this hardware.
  assert.equal(HARDWARE_GPU_FLAGS.includes('--use-gl=desktop'), false)
  assert.ok(HARDWARE_GPU_FLAGS.includes('--ignore-gpu-blocklist'))
  assert.ok(HARDWARE_GPU_FLAGS.includes('--ozone-platform=x11'))
})

test('a lost WebGL context rolls the escalation back', () => {
  const { shouldRollBack } = require('../src/gpu-mode')
  assert.equal(shouldRollBack({ webgl2: false, tried: true }), true)
  assert.equal(shouldRollBack({ webgl2: true, tried: true }), false)
  assert.equal(shouldRollBack({ webgl2: false, tried: false }), false)
})
