/**
 * WebSocket transport.
 *
 * Two things the old codebase got wrong and this deliberately does not:
 *
 * 1. The scheme is derived from `location.protocol`, never hardcoded. A
 *    hardcoded `wss://` against a plaintext server fails the handshake and
 *    the failure is invisible.
 * 2. There is an `onerror`/`onclose` path that says something. A viewer that
 *    silently stops updating is indistinguishable from a paused world.
 */

const RECONNECT_MS = 1000
const MAX_BACKOFF_MS = 8000

export function connect({ onScene, onFrame, onStatus }) {
  let socket = null
  let backoff = RECONNECT_MS
  let closedByUs = false

  const url = () => {
    const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${scheme}//${location.host}/ws/view`
  }

  function open() {
    onStatus('connecting…', true)
    socket = new WebSocket(url())

    socket.onopen = () => {
      backoff = RECONNECT_MS
      onStatus('connected', true)
    }

    socket.onmessage = (event) => {
      let msg
      try {
        msg = JSON.parse(event.data)
      } catch {
        return // a malformed frame is not worth tearing the connection down
      }

      if (msg.type === 'scene') onScene(msg)
      else if (msg.type === 'frame') onFrame(msg)
    }

    socket.onerror = () => {
      onStatus('connection error', false)
    }

    socket.onclose = () => {
      if (closedByUs) return
      onStatus(`disconnected — retrying in ${Math.round(backoff / 1000)}s`, false)
      setTimeout(open, backoff)
      backoff = Math.min(MAX_BACKOFF_MS, backoff * 2)
    }
  }

  open()

  return {
    send(message) {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(message))
      }
    },
    close() {
      closedByUs = true
      socket?.close()
    },
  }
}
