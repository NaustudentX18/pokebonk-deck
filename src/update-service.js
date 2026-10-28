'use strict'

const { checkBuild } = require('./version-probe')

/**
 * Polls the upstream build id and reports when it changes.
 *
 * The first probe of a fresh install is treated as a baseline, not an
 * "update": a first-time user should not be told to reload a build they
 * have never played.
 */
function createUpdateService({
  probe,
  getLastBuild,
  setLastBuild,
  onUpdate,
  timer = setInterval,
  clear = clearInterval
}) {
  let handle = null

  async function checkNow() {
    const info = await probe()
    if (!info) return null

    const previous = getLastBuild()
    const { changed } = checkBuild({ current: info.build, previous })
    setLastBuild(info.build)

    if (changed && previous !== null) onUpdate(info)
    return info
  }

  return {
    checkNow,
    start(intervalMs = 30 * 60 * 1000) {
      if (handle) return
      handle = timer(() => { void checkNow() }, intervalMs)
      if (typeof handle.unref === 'function') handle.unref()
    },
    stop() {
      if (!handle) return
      clear(handle)
      handle = null
    }
  }
}

module.exports = { createUpdateService }
