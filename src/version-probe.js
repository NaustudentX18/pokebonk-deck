'use strict'

/**
 * Upstream build detection.
 *
 * pokebonk.com publishes its current build as JSON at /version.json. The
 * endpoint sends no Access-Control-Allow-Origin header, so it must be fetched
 * out-of-process (Electron's main process), never from inside the page.
 *
 * The `build` id changes with every upstream release; the `version` is the
 * human-readable semver.
 */

const VERSION_URL = 'https://pokebonk.com/version.json'

/** Compare a freshly probed build id against the last one we saw. */
function checkBuild({ current, previous }) {
  return { changed: current !== previous, next: current }
}

/**
 * Fetch the upstream build info.
 * @param {Function} [fetchImpl] injectable fetch, for tests
 * @returns {Promise<{build: string, version: string}|null>} null on any failure
 */
async function probeVersion(fetchImpl = globalThis.fetch) {
  try {
    const res = await fetchImpl(`${VERSION_URL}?t=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) return null
    const data = await res.json()
    if (typeof data?.build !== 'string' || !data.build) return null
    return { build: data.build, version: String(data.version ?? '') }
  } catch {
    return null
  }
}

module.exports = { VERSION_URL, checkBuild, probeVersion }
