import { ref, onUnmounted } from 'vue'

interface SessionMessage {
  role: string
  content: string
  created_at: string
}

interface SessionEvent {
  event: string
  session_key: string
  message: SessionMessage
}

export function useSessionWS() {
  const events = ref<SessionEvent[]>([])
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    ws = new WebSocket(`${proto}://${location.host}/ws/sessions`)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        if (data.event === 'new_message') {
          events.value.push(data)
          // Keep buffer manageable
          if (events.value.length > 500) {
            events.value = events.value.slice(-250)
          }
        }
      } catch {
        // ignore
      }
    }

    ws.onclose = () => {
      connected.value = false
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

  onUnmounted(disconnect)

  return { events, connected, connect, disconnect }
}
