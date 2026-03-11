<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NInput, NButton } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ChatBubble from '../components/ChatBubble.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const sessions = ref<any[]>([])
const selectedKey = ref<string | null>(null)
const messages = ref<any[]>([])
const loadingMessages = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

// Chat input state
const input = ref('')
const sending = ref(false)
const thinking = ref(false)
const wsConnected = ref(false)
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

function formatDate(dateStr: string | null): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 86400000) {
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
  if (diff < 604800000) {
    return d.toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function loadSessions() {
  try {
    const { data } = await api.get('/sessions')
    sessions.value = data
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

async function selectSession(key: string) {
  selectedKey.value = key
  router.replace(`/sessions/${encodeURIComponent(key)}`)
  loadingMessages.value = true
  try {
    const { data } = await api.get(`/sessions/${encodeURIComponent(key)}/messages`)
    messages.value = data
    scrollToBottom()
  } catch {
    messages.value = []
  } finally {
    loadingMessages.value = false
  }
}

// WebSocket connection for chat
function connectWs() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/ws/chat`
  ws = new WebSocket(url)

  ws.onopen = () => {
    wsConnected.value = true
  }

  ws.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data)
      if (parsed.type === 'ping') return
      if (parsed.type === 'ack') {
        thinking.value = true
      } else if (parsed.type === 'thinking') {
        thinking.value = true
      } else if (parsed.type === 'response') {
        thinking.value = false
        sending.value = false
        messages.value.push({
          role: 'assistant',
          content: parsed.content,
          created_at: new Date().toISOString(),
        })
        scrollToBottom()
        // Refresh sessions list to update message counts
        loadSessions()
      } else if (parsed.type === 'error') {
        thinking.value = false
        sending.value = false
        messages.value.push({
          role: 'assistant',
          content: `Error: ${parsed.error}`,
          created_at: new Date().toISOString(),
        })
        scrollToBottom()
      }
    } catch {
      // ignore non-JSON
    }
  }

  ws.onclose = () => {
    wsConnected.value = false
    reconnectTimer = setTimeout(connectWs, 3000)
  }

  ws.onerror = () => {
    wsConnected.value = false
  }
}

function disconnectWs() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
}

function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value || !selectedKey.value) return
  messages.value.push({
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  })
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'message',
      content: text,
      session_key: selectedKey.value,
    }))
  }
  input.value = ''
  sending.value = true
  scrollToBottom()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    sendMessage()
  }
}

onMounted(async () => {
  connectWs()
  await loadSessions()
  const key = route.params.key as string
  if (key && sessions.value.length > 0) {
    await selectSession(decodeURIComponent(key))
  } else if (sessions.value.length > 0) {
    await selectSession(sessions.value[0].session_key)
  }
})

onUnmounted(() => {
  disconnectWs()
})
</script>

<template>
  <PageLayout title="Sessions" description="View and continue conversation history">
    <div v-if="loading" class="sessions-layout">
      <div class="session-list">
        <SkeletonCard v-for="i in 5" :key="i" :lines="1" />
      </div>
      <div class="session-detail">
        <SkeletonCard :lines="3" />
      </div>
    </div>

    <template v-else-if="sessions.length === 0">
      <EmptyState icon="&#9678;" title="No sessions yet" description="Sessions will appear here once users start chatting." />
    </template>

    <div v-else class="sessions-layout">
      <!-- Session List -->
      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.session_key"
          class="session-item"
          :class="{ active: selectedKey === s.session_key }"
          @click="selectSession(s.session_key)"
        >
          <div class="session-header">
            <div class="session-title">{{ s.preview || s.session_key }}</div>
            <div class="session-date">{{ formatDate(s.updated_at) }}</div>
          </div>
          <div class="session-meta">
            <span v-if="s.channel" class="session-channel">{{ s.channel }}</span>
            <span>{{ s.message_count || 0 }} msgs</span>
          </div>
          <div class="session-key">{{ s.session_key }}</div>
        </div>
      </div>

      <!-- Message Detail -->
      <div class="session-detail-wrapper">
        <div class="session-detail" ref="messagesEl">
          <template v-if="selectedKey">
            <div v-if="loadingMessages" class="detail-loading">
              <SkeletonCard :lines="3" />
            </div>
            <template v-else-if="messages.length === 0">
              <EmptyState title="No messages" description="This session has no messages." />
            </template>
            <div v-else class="message-flow">
              <ChatBubble
                v-for="(msg, i) in messages"
                :key="msg.id || i"
                :role="msg.role"
                :content="msg.content || ''"
                :tool-calls="msg.tool_calls"
                :created-at="msg.created_at"
              />
              <div v-if="thinking" class="thinking-indicator">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>
            </div>
          </template>
          <template v-else>
            <EmptyState title="Select a session" description="Choose a session from the list to view messages." />
          </template>
        </div>

        <!-- Chat Input - always visible when a session is selected -->
        <div v-if="selectedKey" class="chat-input-area">
          <div class="connection-status" :class="{ online: wsConnected }">
            {{ wsConnected ? 'Connected' : 'Disconnected' }}
          </div>
          <div class="input-row">
            <NInput
              v-model:value="input"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="Continue the conversation..."
              :disabled="!wsConnected"
              @keydown="handleKeydown"
            />
            <NButton
              type="primary"
              :loading="sending"
              :disabled="!input.trim() || !wsConnected"
              @click="sendMessage"
            >
              Send
            </NButton>
          </div>
        </div>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.sessions-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: var(--space-4);
  min-height: 60vh;
}
.session-list {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  overflow-y: auto;
  max-height: 75vh;
}
.session-item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 150ms;
}
.session-item:hover {
  background: var(--bg-muted);
}
.session-item.active {
  background: var(--bg-muted);
  border-left: 2px solid var(--text-primary);
}
.session-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--space-2);
}
.session-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.session-date {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
  flex-shrink: 0;
}
.session-meta {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.session-channel {
  text-transform: capitalize;
}
.session-key {
  font-size: 11px;
  color: var(--text-muted);
  opacity: 0.6;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: monospace;
}
.session-detail-wrapper {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: 75vh;
}
.session-detail {
  flex: 1;
  padding: var(--space-6);
  overflow-y: auto;
}
.message-flow {
  display: flex;
  flex-direction: column;
}
.chat-input-area {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding: var(--space-3) var(--space-4);
}
.connection-status {
  font-size: var(--text-xs);
  color: var(--accent-red);
  margin-bottom: var(--space-2);
}
.connection-status.online {
  color: var(--accent-green, #22c55e);
}
.input-row {
  display: flex;
  gap: var(--space-3);
  align-items: flex-end;
}
.input-row :deep(.n-input) {
  flex: 1;
}
.thinking-indicator {
  display: flex;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: blink 1.4s infinite both;
}
.dot:nth-child(2) { animation-delay: 0.2s; }
.dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}

@media (max-width: 767px) {
  .sessions-layout {
    grid-template-columns: 1fr;
  }
  .session-list {
    max-height: 40vh;
  }
}
</style>
