<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NInput, NButton, NCheckbox } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ChatBubble from '../components/ChatBubble.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import ChannelTree from '../components/ChannelTree.vue'
import KnowhowSidebar from '../components/KnowhowSidebar.vue'
import KnowhowPreview from '../components/KnowhowPreview.vue'
import { useSessionWS } from '../composables/useSessionWS'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
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

// Know-how extraction state
const selecting = ref(false)
const selectedMsgIds = ref(new Set<number>())
const showKnowhowPreview = ref(false)
const extractMsgIds = ref<number[]>([])

// Session WS for real-time updates
const sessionWS = useSessionWS()

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function selectSession(key: string) {
  selectedKey.value = key
  router.replace(`/sessions/${encodeURIComponent(key)}`)
  loadingMessages.value = true
  selecting.value = false
  selectedMsgIds.value.clear()
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

// Watch session WS events for real-time message updates
watch(() => sessionWS.events.value.length, () => {
  const latest = sessionWS.events.value[sessionWS.events.value.length - 1]
  if (latest && latest.session_key === selectedKey.value) {
    messages.value.push({
      role: latest.message.role,
      content: latest.message.content,
      created_at: latest.message.created_at,
    })
    scrollToBottom()
  }
})

// WebSocket connection for chat
function connectWs() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${window.location.host}/ws/chat`
  ws = new WebSocket(url)

  ws.onopen = () => { wsConnected.value = true }

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
    } catch { /* ignore */ }
  }

  ws.onclose = () => {
    wsConnected.value = false
    reconnectTimer = setTimeout(connectWs, 3000)
  }

  ws.onerror = () => { wsConnected.value = false }
}

function disconnectWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  if (ws) { ws.close(); ws = null }
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

// Know-how extraction
function toggleMsgSelect(id: number) {
  if (selectedMsgIds.value.has(id)) selectedMsgIds.value.delete(id)
  else selectedMsgIds.value.add(id)
}

function startExtract() {
  extractMsgIds.value = [...selectedMsgIds.value]
  showKnowhowPreview.value = true
}

function onKnowhowSaved() {
  selecting.value = false
  selectedMsgIds.value.clear()
}

function navigateKnowhow(id: string) {
  router.push(`/knowhow/${id}`)
}

onMounted(async () => {
  connectWs()
  sessionWS.connect()
  loading.value = false
  const key = route.params.key as string
  if (key) {
    await selectSession(decodeURIComponent(key))
  }
})

onUnmounted(() => {
  disconnectWs()
  sessionWS.disconnect()
})
</script>

<template>
  <PageLayout title="Sessions" description="View and continue conversation history">
    <div class="sessions-layout">
      <!-- Sidebar: Channel Tree + Know-how -->
      <div class="sidebar">
        <div class="sidebar-top">
          <ChannelTree :selected-key="selectedKey" @select="selectSession" />
        </div>
        <div class="sidebar-bottom">
          <KnowhowSidebar @select="navigateKnowhow" />
        </div>
      </div>

      <!-- Message Detail -->
      <div class="session-detail-wrapper">
        <!-- Toolbar -->
        <div v-if="selectedKey" class="toolbar">
          <span class="toolbar-title">{{ selectedKey }}</span>
          <n-button
            v-if="!selecting"
            size="small"
            quaternary
            @click="selecting = true"
          >
            Extract Know-how
          </n-button>
          <template v-if="selecting">
            <span class="select-count">{{ selectedMsgIds.size }} selected</span>
            <n-button
              v-if="selectedMsgIds.size >= 2"
              size="small"
              type="primary"
              @click="startExtract"
            >
              Save as Know-how
            </n-button>
            <n-button size="small" @click="selecting = false; selectedMsgIds.clear()">
              Cancel
            </n-button>
          </template>
        </div>

        <div class="session-detail" ref="messagesEl">
          <template v-if="selectedKey">
            <div v-if="loadingMessages" class="detail-loading">
              <SkeletonCard :lines="3" />
            </div>
            <template v-else-if="messages.length === 0">
              <EmptyState title="No messages" description="This session has no messages." />
            </template>
            <div v-else class="message-flow">
              <div
                v-for="(msg, i) in messages"
                :key="msg.id || i"
                class="message-row"
                :class="{ selectable: selecting }"
                @click="selecting && msg.id ? toggleMsgSelect(msg.id) : null"
              >
                <n-checkbox
                  v-if="selecting && msg.id"
                  :checked="selectedMsgIds.has(msg.id)"
                  class="msg-checkbox"
                  @update:checked="toggleMsgSelect(msg.id)"
                />
                <ChatBubble
                  :role="msg.role"
                  :content="msg.content || ''"
                  :tool-calls="msg.tool_calls"
                  :created-at="msg.created_at"
                  style="flex: 1; min-width: 0"
                />
              </div>
              <div v-if="thinking" class="thinking-indicator">
                <span class="dot" /><span class="dot" /><span class="dot" />
              </div>
            </div>
          </template>
          <template v-else>
            <EmptyState title="Select a session" description="Choose a session from the sidebar." />
          </template>
        </div>

        <!-- Chat Input -->
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

    <!-- Know-how Preview Modal -->
    <KnowhowPreview
      :session-key="selectedKey || ''"
      :message-ids="extractMsgIds"
      :show="showKnowhowPreview"
      @update:show="showKnowhowPreview = $event"
      @saved="onKnowhowSaved"
    />
  </PageLayout>
</template>

<style scoped>
.sessions-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: var(--space-4);
  min-height: 60vh;
}
.sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: 80vh;
  overflow: hidden;
}
.sidebar-top {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.sidebar-bottom {
  max-height: 40%;
  border-top: 2px solid var(--border);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.toolbar-title {
  flex: 1;
  font-size: var(--text-sm);
  font-family: monospace;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.select-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.session-detail-wrapper {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: 80vh;
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
.message-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
}
.message-row.selectable {
  cursor: pointer;
  border-radius: var(--radius-md);
  padding: 2px;
}
.message-row.selectable:hover {
  background: var(--bg-muted);
}
.msg-checkbox {
  margin-top: 8px;
  flex-shrink: 0;
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
  .sidebar {
    max-height: 40vh;
  }
}
</style>
