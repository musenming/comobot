<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
import { NInput, NButton, NCheckbox } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import { useI18n } from '../composables/useI18n'
import ChatBubble from '../components/ChatBubble.vue'
import ChannelTree from '../components/ChannelTree.vue'
import KnowhowPreview from '../components/KnowhowPreview.vue'
import { useWebSocket } from '../composables/useWebSocket'
import { useSessionWS } from '../composables/useSessionWS'
import api from '../api/client'

const { t } = useI18n()

interface ToolStep {
  name: string
  content: string
  done: boolean
  startTime: number
}

interface ChatMessage {
  id?: number
  role: 'user' | 'assistant'
  content: string
  toolSteps?: ToolStep[]
  created_at?: string
}

const SESSION_STORAGE_KEY = 'comobot-current-session'
const PAGE_SIZE = 200

const { connected, data, send } = useWebSocket('/ws/chat')
const sessionWS = useSessionWS()
const chatMessages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const thinking = ref(false)
const toolHint = ref('')
const messagesEl = ref<HTMLElement | null>(null)
const currentSessionKey = ref<string>('')
const currentSessionTitle = ref<string>('')
const hasMoreMessages = ref(false)
const loadingMore = ref(false)
const currentOffset = ref(0)
const channelTreeRef = ref<InstanceType<typeof ChannelTree> | null>(null)
let reloadTimer: ReturnType<typeof setTimeout> | null = null
function debouncedReloadTree() {
  if (reloadTimer) clearTimeout(reloadTimer)
  reloadTimer = setTimeout(() => channelTreeRef.value?.reload(), 1000)
}

// Active workflow steps collected during a single assistant turn
const activeToolSteps = ref<ToolStep[]>([])
const workflowCollapsed = ref<Record<number, boolean>>({})

// Know-how extraction state
const selecting = ref(false)
const selectedMsgIds = ref(new Set<number>())
const showKnowhowPreview = ref(false)
const extractMsgIds = ref<number[]>([])

// File upload state
interface AttachedFile {
  id: string
  file: File
  name: string
  size: number
  type: string
  url?: string        // set after upload
  uploading: boolean
  error?: string
}

const attachedFiles = ref<AttachedFile[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const uploading = ref(false)

const hasFiles = computed(() => attachedFiles.value.length > 0)

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function getFileIcon(type: string, name: string): string {
  if (type.startsWith('image/')) return '🖼'
  if (type.startsWith('audio/')) return '🎵'
  if (type === 'application/pdf') return '📄'
  const ext = name.split('.').pop()?.toLowerCase() || ''
  if (['py', 'js', 'ts', 'vue', 'jsx', 'tsx', 'java', 'go', 'rs', 'cpp', 'c', 'h'].includes(ext)) return '💻'
  if (['zip', 'tar', 'gz'].includes(ext)) return '📦'
  if (['csv', 'xls', 'xlsx'].includes(ext)) return '📊'
  if (['doc', 'docx', 'rtf'].includes(ext)) return '📝'
  return '📎'
}

function openFilePicker() {
  fileInputRef.value?.click()
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files) {
    addFiles(Array.from(input.files))
  }
  // Reset so selecting the same file again triggers change
  input.value = ''
}

function addFiles(files: File[]) {
  for (const file of files) {
    // Skip duplicates by name+size
    if (attachedFiles.value.some(f => f.name === file.name && f.size === file.size)) continue
    attachedFiles.value.push({
      id: Math.random().toString(36).slice(2, 10),
      file,
      name: file.name,
      size: file.size,
      type: file.type || 'application/octet-stream',
      uploading: false,
    })
  }
}

function removeFile(id: string) {
  attachedFiles.value = attachedFiles.value.filter(f => f.id !== id)
}

function clearFiles() {
  attachedFiles.value = []
}

// Drag & drop handlers
function onDragEnter(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}
function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}
function onDragLeave(e: DragEvent) {
  e.preventDefault()
  // Only hide if leaving the drop zone entirely
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
  const { clientX, clientY } = e
  if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) {
    dragOver.value = false
  }
}
function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  if (e.dataTransfer?.files) {
    addFiles(Array.from(e.dataTransfer.files))
  }
}

async function uploadFiles(): Promise<{ name: string; url: string; type: string; size: number }[]> {
  const toUpload = attachedFiles.value.filter(f => !f.url && !f.error)
  if (toUpload.length === 0) {
    return attachedFiles.value.filter(f => f.url).map(f => ({
      name: f.name, url: f.url!, type: f.type, size: f.size,
    }))
  }

  uploading.value = true
  const formData = new FormData()
  for (const f of toUpload) {
    f.uploading = true
    formData.append('files', f.file)
  }

  try {
    const { data: results } = await api.post('/chat/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    // Map results back to attached files
    for (const result of results) {
      const match = toUpload.find(f => f.name === result.name)
      if (match) {
        match.url = result.url
        match.uploading = false
      }
    }
  } catch (e: any) {
    for (const f of toUpload) {
      f.uploading = false
      f.error = e.response?.data?.detail || 'Upload failed'
    }
    throw e
  } finally {
    uploading.value = false
  }

  return attachedFiles.value.filter(f => f.url).map(f => ({
    name: f.name, url: f.url!, type: f.type, size: f.size,
  }))
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

// Load messages for a specific session (latest PAGE_SIZE, with pagination support)
async function loadSessionMessages(sessionKey: string) {
  currentOffset.value = 0
  hasMoreMessages.value = false
  try {
    const { data } = await api.get(
      `/sessions/${encodeURIComponent(sessionKey)}/messages`,
      { params: { limit: PAGE_SIZE, offset: 0 } },
    )
    const msgs = (data || []).map((m: any) => ({
      id: m.id,
      role: m.role,
      content: m.content || '',
      created_at: m.created_at,
    }))
    chatMessages.value = msgs
    hasMoreMessages.value = msgs.length >= PAGE_SIZE
    currentOffset.value = msgs.length
    scrollToBottom()
  } catch {
    // Try web-specific endpoint as fallback
    try {
      const shortKey = sessionKey.replace(/^web:/, '')
      const { data } = await api.get(`/chat/sessions/${encodeURIComponent(shortKey)}/messages`)
      chatMessages.value = (data || []).map((m: any) => ({
        id: m.id,
        role: m.role,
        content: m.content || '',
        created_at: m.created_at,
      }))
      scrollToBottom()
    } catch {
      // Session may not exist in DB yet (new session)
    }
  }
}

// Load older messages when scrolling to top
async function loadOlderMessages() {
  if (loadingMore.value || !hasMoreMessages.value || !currentSessionKey.value) return
  loadingMore.value = true
  try {
    const { data } = await api.get(
      `/sessions/${encodeURIComponent(currentSessionKey.value)}/messages`,
      { params: { limit: PAGE_SIZE, offset: currentOffset.value } },
    )
    const older = (data || []).map((m: any) => ({
      id: m.id,
      role: m.role,
      content: m.content || '',
      created_at: m.created_at,
    }))
    if (older.length > 0) {
      // Preserve scroll position: remember distance from top before prepending
      const el = messagesEl.value
      const prevHeight = el ? el.scrollHeight : 0
      chatMessages.value = [...older, ...chatMessages.value]
      currentOffset.value += older.length
      // Restore scroll position so content doesn't jump
      nextTick(() => {
        if (el) el.scrollTop = el.scrollHeight - prevHeight
      })
    }
    hasMoreMessages.value = older.length >= PAGE_SIZE
  } catch {
    // ignore
  } finally {
    loadingMore.value = false
  }
}

function onMessagesScroll() {
  const el = messagesEl.value
  if (!el) return
  if (el.scrollTop < 100 && hasMoreMessages.value && !loadingMore.value) {
    loadOlderMessages()
  }
}

// Restore or create session on mount
onMounted(async () => {
  sessionWS.connect()
  const saved = localStorage.getItem(SESSION_STORAGE_KEY)
  if (saved) {
    currentSessionKey.value = saved
    currentSessionTitle.value = saved
    await loadSessionMessages(saved)
  } else {
    createNewSession()
  }
})

onUnmounted(() => {
  sessionWS.disconnect()
})

// Watch session WS events for real-time message updates from external channels
// (Telegram, Feishu, etc.). Web-originated messages are NOT broadcast by the
// backend, so there is no risk of duplicates here.
watch(() => sessionWS.events.value.length, () => {
  const latest = sessionWS.events.value[sessionWS.events.value.length - 1]
  if (!latest) return
  if (latest.session_key === currentSessionKey.value) {
    chatMessages.value.push({
      role: latest.message.role as 'user' | 'assistant',
      content: latest.message.content,
      created_at: latest.message.created_at,
    })
    scrollToBottom()
  }
  // Refresh ChannelTree to update message counts / new sessions (debounced)
  debouncedReloadTree()
})

function createNewSession() {
  chatMessages.value = []
  activeToolSteps.value = []
  workflowCollapsed.value = {}
  thinking.value = false
  sending.value = false
  toolHint.value = ''
  selecting.value = false
  selectedMsgIds.value.clear()

  const newKey = `web:${Math.random().toString(36).slice(2, 14)}`
  currentSessionKey.value = newKey
  currentSessionTitle.value = newKey
  localStorage.setItem(SESSION_STORAGE_KEY, newKey)
}

function selectSession(key: string) {
  currentSessionKey.value = key
  currentSessionTitle.value = key
  localStorage.setItem(SESSION_STORAGE_KEY, key)
  chatMessages.value = []
  activeToolSteps.value = []
  workflowCollapsed.value = {}
  thinking.value = false
  sending.value = false
  selecting.value = false
  selectedMsgIds.value.clear()
  loadSessionMessages(key)
}

function handleSessionMeta(meta: { key: string; title: string }) {
  if (meta.key === currentSessionKey.value) {
    currentSessionTitle.value = meta.title
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
    // Keep workflow expanded after completion (user can collapse manually)
    scrollToBottom()
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

async function sendMessage() {
  const text = input.value.trim()
  if ((!text && !hasFiles.value) || sending.value) return

  let fileRefs: { name: string; url: string; type: string; size: number }[] = []

  // Upload files first if any
  if (hasFiles.value) {
    try {
      fileRefs = await uploadFiles()
    } catch {
      // Upload failed — don't send message
      return
    }
  }

  // Build display content: text + file references
  let displayContent = text
  if (fileRefs.length > 0) {
    const fileList = fileRefs.map(f => `📎 ${f.name}`).join('\n')
    displayContent = displayContent ? `${displayContent}\n\n${fileList}` : fileList
  }

  chatMessages.value.push({
    role: 'user',
    content: displayContent,
    created_at: new Date().toISOString(),
  })

  // Build message content for the agent
  let agentContent = text
  if (fileRefs.length > 0) {
    const fileInfo = fileRefs.map(f => `[File: ${f.name} (${f.type}, ${formatFileSize(f.size)}) → ${f.url}]`).join('\n')
    agentContent = agentContent ? `${agentContent}\n\n${fileInfo}` : fileInfo
  }

  send(JSON.stringify({
    type: 'message',
    content: agentContent,
    session_key: currentSessionKey.value,
    files: fileRefs.length > 0 ? fileRefs : undefined,
  }))

  input.value = ''
  clearFiles()
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
  <PageLayout :title="t('chat.title')">
    <template #actions>
      <div class="history-title">{{ t('chat.historySessions') }}</div>
    </template>

    <div class="chat-layout">
      <!-- Main chat area -->
      <div class="chat-container">
        <!-- Toolbar -->
        <div v-if="currentSessionKey" class="toolbar">
          <span class="toolbar-title">{{ currentSessionTitle || currentSessionKey }}</span>
          <n-button
            v-if="!selecting"
            class="extract-knowhow-btn"
            size="small"
            @click="selecting = true"
          >
            {{ t('chat.extractKnowhow') }}
          </n-button>
          <template v-if="selecting">
            <span class="select-count">{{ selectedMsgIds.size }} {{ t('common.selected') }}</span>
            <n-button
              v-if="selectedMsgIds.size >= 2"
              size="small"
              type="primary"
              @click="startExtract"
            >
              {{ t('chat.saveAsKnowhow') }}
            </n-button>
            <n-button size="small" @click="selecting = false; selectedMsgIds.clear()">
              {{ t('common.cancel') }}
            </n-button>
          </template>
        </div>

        <div ref="messagesEl" class="chat-messages" @scroll="onMessagesScroll">
          <div v-if="loadingMore" class="loading-more">{{ t('chat.loadingEarlier') }}</div>
          <div v-if="chatMessages.length === 0 && !thinking" class="chat-empty">
            <span class="empty-icon">&#9651;</span>
            <p>{{ t('chat.startConversation') }}</p>
          </div>

          <template v-for="(msg, i) in chatMessages" :key="i">
            <!-- Workflow steps (collapsible) -->
            <div v-if="msg.toolSteps && msg.toolSteps.length > 0" class="workflow-block">
              <button class="workflow-header" @click="toggleWorkflow(i)">
                <span class="workflow-chevron">{{ workflowCollapsed[i] ? '\u25B6' : '\u25BC' }}</span>
                <span class="workflow-label">{{ t('chat.workflow') }}</span>
                <span class="workflow-count">{{ msg.toolSteps.length }} {{ t('chat.steps') }}</span>
                <span class="workflow-badge done">{{ t('chat.completed') }}</span>
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

            <div
              class="message-row"
              :class="{ selectable: selecting }"
              @click="selecting && msg.id && toggleMsgSelect(msg.id)"
            >
              <n-checkbox
                v-if="selecting && msg.id"
                :checked="selectedMsgIds.has(msg.id)"
                class="msg-checkbox"
                @click.stop
                @update:checked="toggleMsgSelect(msg.id)"
              />
              <ChatBubble
                :role="msg.role"
                :content="msg.content"
                :created-at="msg.created_at"
                style="flex: 1; min-width: 0"
              />
            </div>
          </template>

          <!-- Active workflow steps (while thinking) -->
          <div v-if="thinking && activeToolSteps.length > 0" class="workflow-block active">
            <div class="workflow-header">
              <span class="workflow-chevron">&or;</span>
              <span class="workflow-label">{{ t('chat.working') }}</span>
              <span class="workflow-count">{{ activeToolSteps.length }} {{ t('chat.steps') }}</span>
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

        <div
          class="chat-input-area"
          :class="{ 'drag-over': dragOver }"
          @dragenter="onDragEnter"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop"
        >
          <!-- Drag overlay -->
          <div v-if="dragOver" class="drag-overlay">
            <div class="drag-overlay-content">
              <span class="drag-icon">+</span>
              <span>{{ t('chat.dropFiles') }}</span>
            </div>
          </div>

          <div class="connection-status" :class="{ online: connected }">
            {{ connected ? t('common.connected') : t('common.disconnected') }}
          </div>

          <!-- File preview bar -->
          <div v-if="hasFiles" class="file-preview-bar">
            <div class="file-preview-list">
              <div
                v-for="file in attachedFiles"
                :key="file.id"
                class="file-preview-item"
                :class="{ uploading: file.uploading, error: file.error }"
              >
                <span class="file-icon">{{ getFileIcon(file.type, file.name) }}</span>
                <div class="file-info">
                  <span class="file-name">{{ file.name }}</span>
                  <span class="file-size">{{ formatFileSize(file.size) }}</span>
                </div>
                <button
                  v-if="!file.uploading"
                  class="file-remove"
                  @click="removeFile(file.id)"
                  :title="t('common.delete')"
                >&times;</button>
                <span v-else class="file-spinner" />
              </div>
            </div>
          </div>

          <!-- Hidden file input -->
          <input
            ref="fileInputRef"
            type="file"
            multiple
            style="display: none"
            @change="handleFileSelect"
          />

          <div class="input-row">
            <button
              class="attach-btn"
              :disabled="!connected"
              :title="t('chat.attachFile')"
              @click="openFilePicker"
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <line x1="10" y1="4" x2="10" y2="16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                <line x1="4" y1="10" x2="16" y2="10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
            <NInput
              v-model:value="input"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              :placeholder="t('chat.typeMessage')"
              :disabled="!connected"
              :input-props="({ autocomplete: 'off', name: 'chat-message', 'data-form-type': 'other' } as any)"
              @keydown="handleKeydown"
            />
            <NButton
              type="primary"
              :loading="sending || uploading"
              :disabled="(!input.trim() && !hasFiles) || !connected"
              @click="sendMessage"
            >
              {{ t('common.send') }}
            </NButton>
          </div>
        </div>
      </div>

      <!-- Channel Tree sidebar -->
      <div class="session-sidebar">
        <ChannelTree
          ref="channelTreeRef"
          :selected-key="currentSessionKey"
          @select="selectSession"
          @select-meta="handleSessionMeta"
        />
      </div>
    </div>

    <!-- Know-how Preview Modal -->
    <KnowhowPreview
      :session-key="currentSessionKey"
      :message-ids="extractMsgIds"
      :show="showKnowhowPreview"
      @update:show="showKnowhowPreview = $event"
      @saved="onKnowhowSaved"
    />
  </PageLayout>
</template>

<style scoped>
.chat-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 336px;
  gap: var(--space-4);
  height: calc(100vh - 160px);
}
.session-sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  align-self: stretch;
  justify-self: end;
  width: 336px;
  height: 100%;
  overflow: hidden;
  margin-right: calc(var(--space-4) * -1);
  padding-right: var(--space-4);
  background: linear-gradient(
    270deg,
    var(--bg-subtle) 0,
    var(--bg-subtle) 70%,
    transparent 100%
  );
}
.session-sidebar::before,
.session-sidebar::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  height: 22px;
  pointer-events: none;
  z-index: 2;
}
.session-sidebar::before {
  top: 0;
  background: linear-gradient(to bottom, var(--bg-base), transparent);
}
.session-sidebar::after {
  bottom: 0;
  background: linear-gradient(to top, var(--bg-base), transparent);
}
.history-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: #111;
  line-height: 1.2;
  white-space: nowrap;
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
.extract-knowhow-btn {
  --n-border: 1px solid rgba(59, 130, 246, 0.28);
  --n-border-hover: 1px solid rgba(37, 99, 235, 0.38);
  --n-border-pressed: 1px solid rgba(29, 78, 216, 0.42);
  --n-color: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(99, 102, 241, 0.08));
  --n-color-hover: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(99, 102, 241, 0.15));
  --n-color-pressed: linear-gradient(135deg, rgba(37, 99, 235, 0.24), rgba(79, 70, 229, 0.2));
  --n-text-color: #24407a;
  --n-text-color-hover: #1d3a75;
  --n-text-color-pressed: #17305f;
  --n-border-radius: 999px;
  font-weight: 600;
  letter-spacing: 0.01em;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.12);
  transition: transform 120ms var(--ease-default), box-shadow 160ms var(--ease-default);
}
.extract-knowhow-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.16);
}
.extract-knowhow-btn:active {
  transform: translateY(0);
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.12);
}
.extract-knowhow-btn:deep(.n-button__content) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.extract-knowhow-btn:deep(.n-button__content)::before {
  content: '✦';
  font-size: 11px;
  line-height: 1;
  opacity: 0.88;
}
.select-count {
  font-size: var(--text-xs);
  color: var(--text-secondary);
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
.chat-container {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4) 0;
  min-height: 0;
}
.loading-more {
  text-align: center;
  padding: var(--space-2);
  color: var(--text-muted);
  font-size: var(--text-sm);
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
  position: relative;
  transition: border-color 200ms ease;
}
.chat-input-area.drag-over {
  border-color: var(--accent-blue, #3b82f6);
}
.drag-overlay {
  position: absolute;
  inset: 0;
  z-index: 10;
  background: rgba(59, 130, 246, 0.08);
  border: 2px dashed var(--accent-blue, #3b82f6);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.drag-overlay-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: var(--accent-blue, #3b82f6);
  font-weight: 500;
  font-size: var(--text-sm);
}
.drag-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--accent-blue, #3b82f6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  font-weight: 300;
  line-height: 1;
}

/* File preview bar */
.file-preview-bar {
  margin-bottom: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
}
.file-preview-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.file-preview-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--surface, #fff);
  border: 1px solid var(--border);
  border-radius: 8px;
  max-width: 240px;
  transition: box-shadow 160ms ease, border-color 160ms ease;
}
.file-preview-item:hover {
  border-color: var(--accent-blue, #3b82f6);
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}
.file-preview-item.uploading {
  opacity: 0.7;
}
.file-preview-item.error {
  border-color: var(--accent-red, #ef4444);
  background: rgba(239, 68, 68, 0.04);
}
.file-icon {
  font-size: 18px;
  flex-shrink: 0;
  line-height: 1;
}
.file-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.file-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 150px;
}
.file-size {
  font-size: 10px;
  color: var(--text-muted);
}
.file-remove {
  width: 20px;
  height: 20px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
  transition: background 120ms ease, color 120ms ease;
}
.file-remove:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-red, #ef4444);
}
.file-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent-blue, #3b82f6);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  flex-shrink: 0;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Attach button */
.attach-btn {
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  background: var(--surface, #fff);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  flex-shrink: 0;
  transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
}
.attach-btn:hover:not(:disabled) {
  background: var(--bg-muted);
  border-color: var(--accent-blue, #3b82f6);
  color: var(--accent-blue, #3b82f6);
}
.attach-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
  max-width: 50%;
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
  .history-title {
    display: none;
  }
  .session-sidebar {
    margin-right: 0;
    padding-right: 0;
    background: transparent;
    width: 100%;
    max-height: 40vh;
  }
}
</style>
