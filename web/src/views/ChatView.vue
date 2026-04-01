<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
import { NInput, NButton, NCheckbox } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import { useI18n } from '../composables/useI18n'
import ChatBubble from '../components/ChatBubble.vue'
import PlanExecutionCard from '../components/PlanExecutionCard.vue'
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

interface PlanToolStep {
  name: string
  content: string
  done: boolean
  startTime?: number
}

interface PlanStepData {
  id: string
  description: string
  agent_type?: string
  status?: 'pending' | 'running' | 'done' | 'failed'
  toolSteps?: PlanToolStep[]
  progress?: string
  result_summary?: string
}

interface ChatMessage {
  id?: number
  role: 'user' | 'assistant' | 'process'
  content: string
  toolSteps?: ToolStep[]
  created_at?: string
  processType?: string
  processData?: any
}

const SESSION_STORAGE_KEY = 'comobot-current-session'
const PAGE_SIZE = 200

const { connected, data, send } = useWebSocket('/ws/chat')
const sessionWS = useSessionWS()
const chatMessages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const thinking = ref(false)
const thinkingContent = ref('')  // ReAct thought content from agent reasoning
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

// Parse tool_calls from DB: stored as JSON-encoded string (e.g. '"plan_created"')
function parseProcessType(raw: any): string {
  if (!raw) return ''
  if (typeof raw === 'string') {
    try { const parsed = JSON.parse(raw); if (typeof parsed === 'string') return parsed } catch {}
  }
  return String(raw)
}

// Parse processData: handles double-encoded JSON from database/API layer.
// The backend stores content as json.dumps(data), and the API serializes the
// row with json.dumps() again, so we need to parse twice to get the real object.
function parseProcessData(raw: string | object | undefined): any {
  if (!raw) return {}
  if (typeof raw === 'object') return raw
  try {
    const first = JSON.parse(raw)
    // If first parse gave us a string that looks like JSON, parse again
    if (typeof first === 'string') {
      try { return JSON.parse(first) } catch { return { content: first } }
    }
    // If content field is a string that looks like JSON, parse it too
    if (typeof first.content === 'string' && first.content.startsWith('{')) {
      try { first.content = JSON.parse(first.content) } catch { /* keep as string */ }
    }
    return first
  } catch {
    return { content: String(raw) }
  }
}

// Reconstruct plan state from flat process messages:
// Merges plan_step, tool_hint, progress into the plan_created message
function reconstructPlanState(msgs: ChatMessage[]): ChatMessage[] {
  // Build a set of indices for pre-plan messages (thinking/progress before plan_created)
  // so we can skip them — they are plan preamble, not standalone messages
  const prePlanIndices = new Set<number>()
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i]!
    if (m.role === 'process' && (m.processType === 'thinking' || m.processType === 'progress' || m.processType === 'plan_progress')) {
      // Look ahead: if a plan_created follows (possibly after more thinking/progress), mark as pre-plan
      for (let j = i + 1; j < msgs.length; j++) {
        const next = msgs[j]!
        if (next.role !== 'process') break
        if (next.processType === 'plan_created') { prePlanIndices.add(i); break }
        if (next.processType !== 'thinking' && next.processType !== 'progress' && next.processType !== 'plan_progress') break
      }
    }
  }

  const result: ChatMessage[] = []
  let currentPlan: ChatMessage | null = null
  let pendingToolSteps: ToolStep[] = []

  nextMsg: for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i]!
    if (msg.role !== 'process') {
      // Attach accumulated standalone tool steps to the next assistant message
      if (msg.role === 'assistant' && pendingToolSteps.length > 0) {
        pendingToolSteps.forEach(s => { s.done = true })
        msg.toolSteps = [...pendingToolSteps]
        pendingToolSteps = []
      }
      result.push(msg)
      continue
    }

    // Skip pre-plan preamble messages
    if (prePlanIndices.has(i)) continue

    const pt = msg.processType

    // Thinking messages are transient UI indicators (animated dots) — they are
    // only meaningful during real-time streaming and should never render on reload.
    if (pt === 'thinking' || pt === 'thinking_content') continue

    if (pt === 'plan_created') {
      // Flush any pending standalone tool steps before entering plan context
      pendingToolSteps = []
      // Initialize steps with toolSteps arrays
      if (msg.processData?.steps) {
        for (const step of msg.processData.steps) {
          if (!step.toolSteps) step.toolSteps = []
          if (!step.status) step.status = 'pending'
        }
      }
      currentPlan = msg
      result.push(msg)
      continue
    }

    if (!currentPlan) {
      // No active plan — accumulate standalone tool_hint/progress for workflow block
      if (pt === 'tool_hint') {
        if (pendingToolSteps.length > 0) {
          pendingToolSteps[pendingToolSteps.length - 1]!.done = true
        }
        pendingToolSteps.push({
          name: msg.processData?.content || '',
          content: '',
          done: false,
          startTime: 0,
        })
        continue
      }
      if (pt === 'progress' && pendingToolSteps.length > 0) {
        pendingToolSteps[pendingToolSteps.length - 1]!.content = msg.processData?.content || ''
        continue
      }
      // Absorb progress messages that are preamble to an upcoming standalone workflow.
      // Look ahead: if a standalone tool_hint follows, skip this progress message.
      if (pt === 'progress') {
        for (let j = i + 1; j < msgs.length; j++) {
          const next = msgs[j]!
          if (next.role !== 'process') break
          if (next.processType === 'tool_hint' && !next.processData?.step_id) continue nextMsg
          if (next.processType !== 'progress') break
        }
      }
      // Other process types: keep as-is
      result.push(msg)
      continue
    }

    // Plan-related messages: merge into currentPlan instead of showing separately
    if (pt === 'plan_step') {
      const stepId = msg.processData?.step_id
      const step = (currentPlan.processData.steps as PlanStepData[]).find(s => s.id === stepId)
      if (step) {
        if (msg.processData.status) step.status = msg.processData.status
        if (msg.processData.progress) step.progress = msg.processData.progress
        if (msg.processData.result_summary) step.result_summary = msg.processData.result_summary
        if (msg.processData.agent_type) step.agent_type = msg.processData.agent_type
      }
      continue // absorbed into plan
    }

    if (pt === 'tool_hint' || pt === 'progress') {
      const stepId = msg.processData?.step_id
      if (stepId) {
        const step = (currentPlan.processData.steps as PlanStepData[]).find(s => s.id === stepId)
        if (step) {
          if (!step.toolSteps) step.toolSteps = []
          if (pt === 'tool_hint') {
            // Mark previous tool as done
            if (step.toolSteps.length > 0) {
              step.toolSteps[step.toolSteps.length - 1]!.done = true
            }
            step.toolSteps.push({
              name: msg.processData.content || '',
              content: '',
              done: false,
            })
          } else {
            // progress: update last tool content
            if (step.toolSteps.length > 0) {
              step.toolSteps[step.toolSteps.length - 1]!.content = msg.processData.content || ''
            }
          }
          continue // absorbed into plan
        }
      }
      // No step_id — not plan-related, accumulate for standalone workflow block
      if (pt === 'tool_hint') {
        if (pendingToolSteps.length > 0) {
          pendingToolSteps[pendingToolSteps.length - 1]!.done = true
        }
        pendingToolSteps.push({
          name: msg.processData.content || '',
          content: '',
          done: false,
          startTime: 0,
        })
      } else if (pt === 'progress' && pendingToolSteps.length > 0) {
        pendingToolSteps[pendingToolSteps.length - 1]!.content = msg.processData.content || ''
      }
      continue
    }

    if (pt === 'plan_progress') {
      continue // absorbed
    }

    if (pt === 'plan_complete') {
      currentPlan.processData._planStatus = 'done'
      if (msg.processData?.summary) currentPlan.processData._planSummary = msg.processData.summary
      // Mark all remaining tool steps as done
      for (const step of (currentPlan.processData.steps as PlanStepData[])) {
        if (step.toolSteps) step.toolSteps.forEach(ts => { ts.done = true })
      }
      currentPlan = null
      continue // absorbed
    }

    // Other process types: keep as-is
    result.push(msg)
  }

  // If plan still active, mark completed tool steps as done (persisted state)
  if (currentPlan) {
    for (const step of (currentPlan.processData.steps as PlanStepData[])) {
      if ((step.status === 'done' || step.status === 'failed') && step.toolSteps) {
        step.toolSteps.forEach(ts => { ts.done = true })
      }
    }
  }

  return result
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
    const rawMsgs = (data || []).map((m: any) => {
      if (m.role === 'process') {
        let processData = {}
        try { processData = parseProcessData(m.content) } catch {}
        return {
          id: m.id,
          role: 'process' as const,
          content: '',
          processType: parseProcessType(m.tool_calls),
          processData,
          created_at: m.created_at,
        }
      }
      return {
        id: m.id,
        role: m.role,
        content: m.content || '',
        created_at: m.created_at,
      }
    })
    // Reconstruct plan state from flat process messages
    chatMessages.value = reconstructPlanState(rawMsgs)
    hasMoreMessages.value = rawMsgs.length >= PAGE_SIZE
    currentOffset.value = rawMsgs.length
    scrollToBottom()
  } catch {
    // Try web-specific endpoint as fallback
    try {
      const shortKey = sessionKey.replace(/^web:/, '')
      const { data } = await api.get(`/chat/sessions/${encodeURIComponent(shortKey)}/messages`)
      const rawMsgs = (data || []).map((m: any) => {
        if (m.role === 'process') {
          let processData = {}
          try { processData = parseProcessData(m.content) } catch {}
          return {
            id: m.id,
            role: 'process' as const,
            content: '',
            processType: parseProcessType(m.tool_calls),
            processData,
            created_at: m.created_at,
          }
        }
        return {
          id: m.id,
          role: m.role,
          content: m.content || '',
          created_at: m.created_at,
        }
      })
      chatMessages.value = reconstructPlanState(rawMsgs)
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
    const olderRaw = (data || []).map((m: any) => {
      if (m.role === 'process') {
        let processData = {}
        try { processData = parseProcessData(m.content) } catch {}
        return {
          id: m.id,
          role: 'process' as const,
          content: '',
          processType: parseProcessType(m.tool_calls),
          processData,
          created_at: m.created_at,
        }
      }
      return {
        id: m.id,
        role: m.role,
        content: m.content || '',
        created_at: m.created_at,
      }
    })
    const older = reconstructPlanState(olderRaw)
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

// Helper: find the latest plan_created message in chatMessages
function findLatestPlanMsg(): ChatMessage | null {
  for (let i = chatMessages.value.length - 1; i >= 0; i--) {
    const m = chatMessages.value[i]
    if (m && m.role === 'process' && m.processType === 'plan_created' && m.processData?.steps) {
      return m
    }
  }
  return null
}

// Helper: route a tool_hint/progress into the correct plan step
function routeToolToPlanStep(stepId: string, toolName: string, isHint: boolean, content: string) {
  const planMsg = findLatestPlanMsg()
  if (!planMsg) return false
  const step = (planMsg.processData.steps as PlanStepData[]).find(s => s.id === stepId)
  if (!step) return false

  if (!step.toolSteps) step.toolSteps = []
  if (isHint) {
    // Mark previous tool as done
    if (step.toolSteps.length > 0) {
      step.toolSteps[step.toolSteps.length - 1]!.done = true
    }
    step.toolSteps.push({ name: toolName, content: '', done: false, startTime: Date.now() })
  } else {
    // Progress update: update last tool content
    if (step.toolSteps.length > 0) {
      step.toolSteps[step.toolSteps.length - 1]!.content = content
    }
  }
  return true
}

watch(data, (msg) => {
  if (!msg) return
  if (msg.type === 'ack') {
    thinking.value = true
    activeToolSteps.value = []
  } else if (msg.type === 'thinking') {
    thinking.value = true
  } else if (msg.type === 'thinking_content') {
    // ReAct reasoning: show the agent's thought process
    thinkingContent.value = msg.content || ''
  } else if (msg.type === 'tool_hint') {
    toolHint.value = msg.content
    // If has step_id, route into plan step; otherwise use standalone workflow
    if (msg.step_id) {
      routeToolToPlanStep(msg.step_id, msg.content, true, '')
    } else {
      activeToolSteps.value.push({
        name: msg.content,
        content: '',
        done: false,
        startTime: Date.now(),
      })
      if (activeToolSteps.value.length > 1) {
        activeToolSteps.value[activeToolSteps.value.length - 2]!.done = true
      }
    }
    scrollToBottom()
  } else if (msg.type === 'progress') {
    if (msg.step_id) {
      routeToolToPlanStep(msg.step_id, '', false, msg.content)
    } else if (activeToolSteps.value.length > 0) {
      const last = activeToolSteps.value[activeToolSteps.value.length - 1]
      last!.content = msg.content
    }
  } else if (msg.type === 'response') {
    thinking.value = false
    thinkingContent.value = ''
    sending.value = false
    toolHint.value = ''
    activeToolSteps.value.forEach(s => { s.done = true })
    // Also mark all running plan step tools as done
    const planMsg = findLatestPlanMsg()
    if (planMsg) {
      for (const step of (planMsg.processData.steps as PlanStepData[])) {
        if (step.toolSteps) {
          step.toolSteps.forEach(ts => { ts.done = true })
        }
      }
    }
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
  } else if (msg.type === 'process') {
    const { process_type, session_key, ...rest } = msg

    // plan_step: update existing plan card, don't push separate message
    if (process_type === 'plan_step') {
      const planMsg = findLatestPlanMsg()
      if (planMsg) {
        const step = (planMsg.processData.steps as PlanStepData[]).find(
          (s: any) => s.id === rest.step_id,
        )
        if (step) {
          step.status = rest.status
          if (rest.progress) step.progress = rest.progress
          if (rest.result_summary) step.result_summary = rest.result_summary
          if (rest.agent_type) step.agent_type = rest.agent_type
          // When step finishes, mark its tool steps as done
          if (rest.status === 'done' || rest.status === 'failed') {
            if (step.toolSteps) {
              step.toolSteps.forEach(ts => { ts.done = true })
            }
          }
        }
      }
      scrollToBottom()
      return
    }

    // plan_progress: update plan card status, don't push separate
    if (process_type === 'plan_progress') {
      scrollToBottom()
      return
    }

    // plan_complete: update plan card to done status
    if (process_type === 'plan_complete') {
      const planMsg = findLatestPlanMsg()
      if (planMsg) {
        planMsg.processData._planStatus = 'done'
        if (rest.summary) planMsg.processData._planSummary = rest.summary
      }
      scrollToBottom()
      return
    }

    // For plan_created, ensure steps have toolSteps arrays
    if (process_type === 'plan_created' && rest.steps) {
      for (const step of rest.steps) {
        if (!step.toolSteps) step.toolSteps = []
        if (!step.status) step.status = 'pending'
      }
    }

    // Other process types: push as message
    chatMessages.value.push({
      role: 'process',
      content: '',
      processType: process_type,
      processData: rest,
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
            <!-- Workflow steps (collapsible) — only for non-plan tool steps -->
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

            <!-- Plan execution card (unified plan + workflow view) -->
            <div
              v-if="msg.role === 'process' && msg.processType === 'plan_created'"
              class="plan-card-row"
            >
              <PlanExecutionCard
                :goal="msg.processData?.goal || ''"
                :steps="msg.processData?.steps || []"
                :status="msg.processData?._planStatus || (msg.processData?.steps?.every((s: any) => s.status === 'done') ? 'done' : 'executing')"
                :summary="msg.processData?._planSummary || ''"
                :plan-id="msg.processData?.plan_id"
              />
            </div>

            <!-- Other messages (non-plan process, user, assistant) -->
            <div
              v-else
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
                :process-type="msg.processType"
                :process-data="msg.processData"
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
            <div v-if="thinkingContent" class="thinking-content">{{ thinkingContent }}</div>
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

/* Plan execution card row */
.plan-card-row {
  margin: var(--space-2) 0;
  max-width: 65%;
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
.thinking-content {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  opacity: 0.85;
  padding: 4px 8px;
  border-left: 2px solid var(--border-color);
  white-space: pre-wrap;
  max-height: 80px;
  overflow-y: auto;
  line-height: 1.4;
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
