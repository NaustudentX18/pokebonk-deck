'use strict'

/** Wait for `predicate()` to become true, polling every `intervalMs`. */
async function waitFor(predicate, { timeoutMs = 5000, intervalMs = 50 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  return false
}

module.exports = { waitFor }
