import { ref, onUnmounted } from 'vue'

export function useWebSocket(path: string) {
  const data = ref<any>(null)
  const connected = ref(false)
  const messages = ref<any[]>([])
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}${path}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        if (parsed.type === 'ping') return
        data.value = parsed
        messages.value.push(parsed)
        // Keep buffer reasonable
        if (messages.value.length > 5000) {
          messages.value = messages.value.slice(-2500)
        }
      } catch {
        // ignore non-JSON
      }
    }

    ws.onclose = () => {
      connected.value = false
      // Auto-reconnect after 3s
      reconnectTimer = setTimeout(connect, 3000)
    }

    ws.onerror = () => {
      connected.value = false
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
  }

  function send(msg: string) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(msg)
    }
  }

  function clear() {
    messages.value = []
  }

  connect()

  onUnmounted(disconnect)

  return { data, connected, messages, send, disconnect, clear }
}
