'use strict'

/**
 * Hardware acceleration detection and escalation.
 *
 * The game itself refuses to be happy on a software rasteriser — it shows
 * "Your browser is not using your graphics card" when the WebGL renderer
 * string matches its own pattern. This module uses the same pattern, so the
 * client recognises the situation the game is complaining about.
 *
 * When it happens, the client relaunches itself once with flags that ask
 * Chromium for the real GPU. Doing it that way — react and escalate — is
 * better than forcing the flags on every launch: a normal Desktop Mode run
 * already gets hardware acceleration, so nothing changes there.
 */

/** The game's own pattern, verbatim. */
const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i

/**
 * Flags that make Chromium use the system GPU rather than falling back to a
 * software rasteriser:
 *
 *   --ignore-gpu-blocklist  do not block the GPU because it is blocklisted
 *   --ozone-platform=x11    go through XWayland, which is the path gamescope
 *                           composites most reliably
 *
 * `--use-gl=desktop` is deliberately NOT here: measured on this hardware it
 * turns WebGL2 off entirely (webgl2: false, no renderer at all), which is
 * worse than the software rasteriser it was meant to fix.
 */
const HARDWARE_GPU_FLAGS = [
  '--ignore-gpu-blocklist',
  '--ozone-platform=x11'
]

/** True when the renderer string says we are on a software rasteriser. */
function isSoftwareRenderer(renderer) {
  if (!renderer) return false
  return SOFTWARE_RENDERER.test(String(renderer))
}

/**
 * Should this launch escalate to the hardware flags?
 *
 * Only when the renderer is a software one AND we have not already tried:
 * escalating twice would loop.
 */
function shouldEscalate({ renderer, tried = false } = {}) {
  return isSoftwareRenderer(renderer) && !tried
}

/**
 * Should the escalation be undone?
 *
 * If the flags were applied and WebGL is now GONE (rather than merely
 * software), the flags did more harm than good: roll back to the plain
 * launch rather than sit there with no renderer at all.
 */
function shouldRollBack({ webgl2, tried = false } = {}) {
  return tried && webgl2 === false
}

module.exports = {
  SOFTWARE_RENDERER,
  HARDWARE_GPU_FLAGS,
  isSoftwareRenderer,
  shouldEscalate,
  shouldRollBack
}
