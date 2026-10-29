'use strict'

/**
 * Hardware acceleration.
 *
 * The game shows "Your browser is not using your graphics card" when the
 * WebGL renderer string matches its own software-rasteriser pattern. On the
 * Deck that happens inside gamescope, when Chromium cannot get the AMD GPU
 * and falls back to SwiftShader.
 *
 * The flags below are applied on every launch — by the launcher script and
 * by the client itself, before the window exists — so the first frame already
 * asks for the real GPU. They were chosen by measurement: each one keeps
 * WebGL2 on the hardware renderer. `--use-gl=desktop` is not among them; on
 * this hardware it turns WebGL2 off entirely.
 */

/** The game's own pattern, verbatim. */
const SOFTWARE_RENDERER = /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i

/**
 *   --ignore-gpu-blocklist   do not block the GPU because it is blocklisted
 *   --ozone-platform=x11     XWayland, the path gamescope composites reliably
 *   --disable-gpu-sandbox    the GPU process can open the Deck's DRM node
 *   --use-angle=gl           ANGLE's GL backend (the one the Deck already
 *                            reports as "AMD ... OpenGL 4.6"), not Vulkan
 *
 * `--use-gl=desktop` is deliberately absent: measured here it turns WebGL2
 * off (webgl2: false, no renderer at all).
 */
const HARDWARE_GPU_FLAGS = [
  '--ignore-gpu-blocklist',
  '--ozone-platform=x11',
  '--disable-gpu-sandbox',
  '--use-angle=gl'
]

/**
 * True when this process was not started with the hardware-acceleration flags.
 *
 * The flags have to be real command-line arguments. Applying the same
 * switches with app.commandLine.appendSwitch segfaults the GPU process
 * (exit 139) and the fallback then forces software rendering — the warning
 * we are trying to remove. Measured: the same flags as argv keep WebGL2 on
 * the hardware renderer.
 */
function missingHardwareFlags(argv = process.argv) {
  return HARDWARE_GPU_FLAGS.some((flag) => !argv.includes(flag))
}

/**
 * Should this process exit and start again with the flags on the command line?
 *
 * The launcher script already passes them, so a normal Game Mode start does
 * not relaunch. A direct AppImage start does, once.
 */
function shouldRelaunchForGpu({ failed = false, software = false, argv = process.argv } = {}) {
  if (software || failed) return false
  if (argv.includes('--no-gpu-flags') || argv.includes('--software-rendering')) return false
  return missingHardwareFlags(argv)
}

/** Args for that relaunch: keep whatever else was passed, add the GPU flags. */
function gpuRelaunchArgs(argv = process.argv) {
  const rest = argv.slice(1).filter((arg) => !HARDWARE_GPU_FLAGS.includes(arg))
  return [...rest, ...HARDWARE_GPU_FLAGS]
}

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
  shouldRollBack,
  missingHardwareFlags,
  shouldRelaunchForGpu,
  gpuRelaunchArgs
}
