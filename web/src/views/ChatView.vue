<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { NInput, NButton } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ChatBubble from '../components/ChatBubble.vue'
import { useWebSocket } from '../composables/useWebSocket'
import api from '../api/client'

interface ToolStep {
  name: string
  content: string
  done: boolean
  startTime: number
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  toolSteps?: ToolStep[]
  created_at?: string
}

interface ChatSession {
  session_key: string
  title: string
  preview: string
  message_count: number
  updated_at: string
}

const SESSION_STORAGE_KEY = 'comobot-current-session'

const { connected, data, send } = useWebSocket('/ws/chat')
const chatMessages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const thinking = ref(false)
const toolHint = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const currentSessionKey = ref<string>('')
const sessions = ref<ChatSession[]>([])

// Active workflow steps collected during a single assistant turn
const activeToolSteps = ref<ToolStep[]>([])
const workflowCollapsed = ref<Record<number, boolean>>({})

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

// Load chat sessions list
async function loadSessions() {
  try {
    const { data } = await api.get('/chat/sessions')
    sessions.value = data || []
  } catch {
    // ignore
  }
}

// Load messages for a specific session
async function loadSessionMessages(sessionKey: string) {
  try {
    const shortKey = sessionKey.replace(/^web:/, '')
    const { data } = await api.get(`/chat/sessions/${encodeURIComponent(shortKey)}/messages`)
    chatMessages.value = (data || []).map((m: any) => ({
      role: m.role,
      content: m.content || '',
      created_at: m.created_at,
    }))
    scrollToBottom()
  } catch {
    // Session may not exist in DB yet (new session)
  }
}

// Restore or create session on mount
onMounted(async () => {
  await loadSessions()
  const saved = localStorage.getItem(SESSION_STORAGE_KEY)
  if (saved) {
    currentSessionKey.value = saved
    await loadSessionMessages(saved)
  } else {
    // Auto-create a new session key
    createNewSession()
  }
})

function createNewSession() {
  // Save current messages as a finished session (they're already persisted server-side)
  const oldKey = currentSessionKey.value
  chatMessages.value = []
  activeToolSteps.value = []
  workflowCollapsed.value = {}
  thinking.value = false
  sending.value = false
  toolHint.value = ''

  const newKey = `web:${crypto.randomUUID().slice(0, 12)}`
  currentSessionKey.value = newKey
  localStorage.setItem(SESSION_STORAGE_KEY, newKey)

  // Refresh sessions list to include the old session
  if (oldKey) {
    loadSessions()
  }
}

function selectSession(s: ChatSession) {
  currentSessionKey.value = s.session_key
  localStorage.setItem(SESSION_STORAGE_KEY, s.session_key)
  chatMessages.value = []
  activeToolSteps.value = []
  workflowCollapsed.value = {}
  thinking.value = false
  sending.value = false
  loadSessionMessages(s.session_key)
}

function toggleWorkflow(index: number) {
  workflowCollapsed.value[index] = !workflowCollapsed.value[index]
}

watch(data, (msg) => {
  if (!msg) return
  if (msg.type === 'ack') {
    thinking.value = true
    activeToolSteps.value = []
  } else if (msg.type === 'thinking') {
    thinking.value = true
  } else if (msg.type === 'tool_hint') {
    toolHint.value = msg.content
    // Add a tool step to the workflow
    activeToolSteps.value.push({
      name: msg.content,
      content: '',
      done: false,
      startTime: Date.now(),
    })
    // Mark previous step as done
    if (activeToolSteps.value.length > 1) {
      activeToolSteps.value[activeToolSteps.value.length - 2]!.done = true
    }
    scrollToBottom()
  } else if (msg.type === 'progress') {
    // Update the last tool step content
    if (activeToolSteps.value.length > 0) {
      const last = activeToolSteps.value[activeToolSteps.value.length - 1]
      last!.content = msg.content
    }
  } else if (msg.type === 'response') {
    thinking.value = false
    sending.value = false
    toolHint.value = ''
    // Mark all remaining tool steps as done
    activeToolSteps.value.forEach(s => { s.done = true })
    const toolSteps = activeToolSteps.value.length > 0
      ? [...activeToolSteps.value]
      : undefined
    activeToolSteps.value = []
    chatMessages.value.push({
      role: 'assistant',
      content: msg.content,
      toolSteps,
      created_at: new Date().toISOString(),
    })
    // Auto-collapse the workflow for the new message
    if (toolSteps) {
      workflowCollapsed.value[chatMessages.value.length - 1] = true
    }
    scrollToBottom()
    loadSessions()  // Refresh sidebar
  } else if (msg.type === 'error') {
    thinking.value = false
    sending.value = false
    toolHint.value = ''
    activeToolSteps.value.forEach(s => { s.done = true })
    activeToolSteps.value = []
    chatMessages.value.push({
      role: 'assistant',
      content: `Error: ${msg.error}`,
      created_at: new Date().toISOString(),
    })
    scrollToBottom()
  }
})

function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return
  chatMessages.value.push({
    role: 'user',
    content: text,
    created_at: new Date().toISOString(),
  })
  send(JSON.stringify({
    type: 'message',
    content: text,
    session_key: currentSessionKey.value,
  }))
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

</script>

<template>
  <PageLayout title="Chat">
    <div class="chat-layout">
      <!-- Session sidebar -->
      <div class="session-sidebar">
        <NButton
          type="primary"
          block
          class="new-session-btn"
          @click="createNewSession"
        >
          + New Session
        </NButton>
        <div class="session-list">
          <div
            v-for="s in sessions"
            :key="s.session_key"
            class="session-item"
            :class="{ active: s.session_key === currentSessionKey }"
            @click="selectSession(s)"
          >
            <div class="session-title">{{ s.title || 'New Chat' }}</div>
            <div class="session-meta">{{ s.message_count || 0 }} msgs</div>
          </div>
        </div>
      </div>

      <!-- Main chat area -->
      <div class="chat-container">
        <div ref="messagesEl" class="chat-messages">
          <div v-if="chatMessages.length === 0 && !thinking" class="chat-empty">
            <span class="empty-icon">&#9651;</span>
            <p>Start a conversation with ComoBot</p>
          </div>

          <template v-for="(msg, i) in chatMessages" :key="i">
            <!-- Workflow steps (collapsible) -->
            <div v-if="msg.toolSteps && msg.toolSteps.length > 0" class="workflow-block">
              <button class="workflow-header" @click="toggleWorkflow(i)">
                <span class="workflow-chevron">{{ workflowCollapsed[i] ? '\u25B6' : '\u25BC' }}</span>
                <span class="workflow-label">Workflow</span>
                <span class="workflow-count">{{ msg.toolSteps.length }} steps</span>
                <span class="workflow-badge done">Completed</span>
              </button>
              <div v-if="!workflowCollapsed[i]" class="workflow-steps">
                <div
                  v-for="(step, si) in msg.toolSteps"
                  :key="si"
                  class="workflow-step"
                >
                  <span class="step-icon" :class="{ completed: step.done }">
                    {{ step.done ? '\u2713' : '\u25CB' }}
                  </span>
                  <span class="step-name">{{ step.name }}</span>
                </div>
              </div>
            </div>

            <ChatBubble
              :role="msg.role"
              :content="msg.content"
              :created-at="msg.created_at"
            />
          </template>

          <!-- Active workflow steps (while thinking) -->
          <div v-if="thinking && activeToolSteps.length > 0" class="workflow-block active">
            <div class="workflow-header">
              <span class="workflow-chevron">&or;</span>
              <span class="workflow-label">Working...</span>
              <span class="workflow-count">{{ activeToolSteps.length }} steps</span>
            </div>
            <div class="workflow-steps">
              <div
                v-for="(step, si) in activeToolSteps"
                :key="si"
                class="workflow-step"
                :class="{ running: !step.done && si === activeToolSteps.length - 1 }"
              >
                <span class="step-icon" :class="{ completed: step.done, running: !step.done && si === activeToolSteps.length - 1 }">
                  {{ step.done ? '\u2713' : '\u25CB' }}
                </span>
                <span class="step-name">{{ step.name }}</span>
              </div>
            </div>
          </div>

          <div v-if="thinking" class="thinking-indicator">
            <div v-if="toolHint && activeToolSteps.length === 0" class="tool-hint">{{ toolHint }}</div>
            <div class="thinking-dots">
              <span class="dot" /><span class="dot" /><span class="dot" />
            </div>
          </div>
        </div>

        <div class="chat-input-area">
          <div class="connection-status" :class="{ online: connected }">
            {{ connected ? 'Connected' : 'Disconnected' }}
          </div>
          <div class="input-row">
            <NInput
              v-model:value="input"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="Type a message..."
              :disabled="!connected"
              @keydown="handleKeydown"
            />
            <NButton
              type="primary"
              :loading="sending"
              :disabled="!input.trim() || !connected"
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
.chat-layout {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: var(--space-4);
  height: calc(100vh - 160px);
}
.session-sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  overflow: hidden;
}
.new-session-btn {
  margin: var(--space-3);
  flex-shrink: 0;
}
.session-list {
  flex: 1;
  overflow-y: auto;
}
.session-item {
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background 150ms;
}
.session-item:hover {
  background: var(--bg-muted);
}
.session-item.active {
  background: var(--bg-muted);
  border-left: 2px solid var(--text-primary);
}
.session-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.chat-container {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) 0;
}
.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: var(--space-3);
}
.empty-icon {
  font-size: 48px;
  opacity: 0.3;
}
.chat-input-area {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
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

/* Workflow block */
.workflow-block {
  margin: var(--space-2) 0;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface);
  overflow: hidden;
}
.workflow-block.active {
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 0 0 1px var(--accent-blue, #3b82f6);
}
.workflow-header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  width: 100%;
  background: var(--bg-muted);
  border: none;
  cursor: pointer;
  color: var(--text-secondary);
  font-family: inherit;
  font-size: var(--text-sm);
  text-align: left;
}
.workflow-header:hover {
  background: var(--border);
}
.workflow-chevron {
  font-size: 10px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}
.workflow-label {
  font-weight: 500;
  color: var(--text-primary);
}
.workflow-count {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-left: auto;
}
.workflow-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 9999px;
  font-weight: 500;
}
.workflow-badge.done {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.workflow-steps {
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--border);
}
.workflow-step {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 3px 0;
  font-size: var(--text-sm);
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  color: var(--text-secondary);
}
.workflow-step.running {
  color: var(--accent-blue, #3b82f6);
}
.step-icon {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 1.5px solid var(--text-muted);
  color: var(--text-muted);
}
.step-icon.completed {
  background: #22c55e;
  border-color: #22c55e;
  color: #fff;
}
.step-icon.running {
  border-color: var(--accent-blue, #3b82f6);
  color: var(--accent-blue, #3b82f6);
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.step-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Thinking indicator */
.thinking-indicator {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
}
.tool-hint {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: var(--text-xs);
  color: var(--text-muted);
  opacity: 0.8;
  padding: 2px 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.thinking-dots {
  display: flex;
  gap: 4px;
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
  .chat-layout {
    grid-template-columns: 1fr;
  }
  .session-sidebar {
    max-height: 150px;
  }
}
</style>
