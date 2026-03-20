<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NButton, NInput, NForm, NFormItem, NTabs, NTabPane, NSelect, NSpace, NCard, NSwitch, useMessage } from 'naive-ui'
import { MdEditor, MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import PageLayout from '../components/PageLayout.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { useThemeStore } from '../stores/theme'
import api, { restartGateway } from '../api/client'

const message = useMessage()
const themeStore = useThemeStore()

// Password
const passwordForm = ref({ new_password: '', confirm_password: '' })
const savingPassword = ref(false)

// Agent files — unified editor
const agentFiles = ref<Record<string, string>>({
  'SOUL.md': '',
  'USER.md': '',
  'AGENTS.md': '',
})
const activeAgentFile = ref('SOUL.md')
const savingAgent = ref(false)

// Memory (read only)
const memoryContent = ref('')

// Danger zone
const showClearMemory = ref(false)

// QMD
const qmdEnabled = ref(false)
const qmdLoading = ref(false)
const qmdStatus = ref<{ state: string; model_memory_mb: number } | null>(null)
const reindexing = ref(false)
const qmdGpu = ref<{ available: boolean; name: string | null }>({ available: true, name: null })
const showNoGpuConfirm = ref(false)

const statusLabel = computed(() => {
  switch (qmdStatus.value?.state) {
    case 'running': return 'Running'
    case 'stopped': return 'Stopped'
    case 'starting': return 'Initializing (first-time setup may take a few minutes)...'
    case 'error': return 'Failed'
    default: return 'Unknown'
  }
})

const themeOptions = [
  { label: 'Dark', value: 'dark' },
  { label: 'Light', value: 'light' },
  { label: 'System', value: 'system' },
]

const agentFileOptions = [
  { label: 'SOUL.md', value: 'SOUL.md' },
  { label: 'USER.md', value: 'USER.md' },
  { label: 'AGENTS.md', value: 'AGENTS.md' },
]

const currentContent = computed({
  get: () => agentFiles.value[activeAgentFile.value] || '',
  set: (v: string) => { agentFiles.value[activeAgentFile.value] = v },
})

onMounted(async () => {
  try {
    const [soul, user, agents, memory] = await Promise.all([
      api.get('/settings/soul'),
      api.get('/settings/user'),
      api.get('/settings/agents').catch(() => ({ data: { content: '' } })),
      api.get('/settings/memory'),
    ])
    agentFiles.value['SOUL.md'] = soul.data.content || ''
    agentFiles.value['USER.md'] = user.data.content || ''
    agentFiles.value['AGENTS.md'] = agents.data.content || ''
    memoryContent.value = memory.data.content || ''
  } catch {
    // May fail if files don't exist yet
  }
  loadQMDStatus()
})

async function savePassword() {
  if (passwordForm.value.new_password.length < 8) {
    message.warning('Password must be at least 8 characters')
    return
  }
  if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
    message.warning('Passwords do not match')
    return
  }
  savingPassword.value = true
  try {
    await api.put('/settings/password', { new_password: passwordForm.value.new_password })
    message.success('Password updated')
    passwordForm.value = { new_password: '', confirm_password: '' }
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to update password')
  } finally {
    savingPassword.value = false
  }
}

async function saveAgentFile() {
  savingAgent.value = true
  const fileMap: Record<string, string> = {
    'SOUL.md': '/settings/soul',
    'USER.md': '/settings/user',
    'AGENTS.md': '/settings/agents',
  }
  const endpoint = fileMap[activeAgentFile.value]
  if (!endpoint) return
  try {
    await api.put(endpoint, { content: currentContent.value })
    message.success(`${activeAgentFile.value} saved, restarting gateway...`)
    restartGateway()
  } catch {
    message.error('Failed to save')
  } finally {
    savingAgent.value = false
  }
}

async function handleClearMemory() {
  try {
    await api.delete('/settings/memory')
    memoryContent.value = '# Memory\n\n'
    message.success('Memory cleared')
  } catch {
    message.error('Failed to clear memory')
  }
}

// QMD functions
async function loadQMDStatus() {
  try {
    const { data } = await api.get('/settings/qmd')
    qmdEnabled.value = data.enabled
    qmdStatus.value = data.status
    if (data.gpu) {
      qmdGpu.value = data.gpu
    }
  } catch {
    // QMD endpoints may not be available
  }
}

async function toggleQMD(value: boolean) {
  // If enabling without GPU, show confirmation dialog first
  if (value && !qmdGpu.value.available) {
    showNoGpuConfirm.value = true
    return
  }
  doToggleQMD(value)
}

function confirmNoGpuStart() {
  showNoGpuConfirm.value = false
  doToggleQMD(true)
}

async function doToggleQMD(value: boolean) {
  qmdLoading.value = true
  if (value && qmdStatus.value) {
    qmdStatus.value = { ...qmdStatus.value, state: 'starting' }
  }
  try {
    const { data } = await api.put('/settings/qmd', { enabled: value })
    if (data.ok) {
      qmdEnabled.value = value
      if (data.state === 'starting') {
        // Background initialization — poll for completion
        message.info('QMD is initializing (first run may take a few minutes)...')
        pollQMDUntilReady()
      } else {
        if (qmdStatus.value) {
          qmdStatus.value = { ...qmdStatus.value, state: data.state || 'stopped' }
        }
        message.success(value ? 'QMD enabled' : 'QMD disabled')
        qmdLoading.value = false
      }
    } else {
      message.error(data.error || 'Failed to toggle QMD')
      qmdEnabled.value = !value
      if (qmdStatus.value) {
        qmdStatus.value = { ...qmdStatus.value, state: 'stopped' }
      }
      qmdLoading.value = false
    }
  } catch (e: any) {
    const detail = e.response?.data?.detail || 'Failed to toggle QMD'
    message.error(detail)
    qmdEnabled.value = !value
    if (qmdStatus.value) {
      qmdStatus.value = { ...qmdStatus.value, state: 'stopped' }
    }
    qmdLoading.value = false
  }
}

async function pollQMDUntilReady(maxWait = 600000) {
  const start = Date.now()
  while (Date.now() - start < maxWait) {
    await new Promise(r => setTimeout(r, 3000))
    try {
      const { data } = await api.get('/settings/qmd')
      qmdStatus.value = data.status
      qmdEnabled.value = data.enabled
      if (data.status.state === 'running') {
        message.success('QMD enabled successfully')
        qmdLoading.value = false
        return
      }
      if (data.status.state === 'error') {
        message.error(data.error || 'QMD initialization failed')
        qmdEnabled.value = false
        qmdLoading.value = false
        return
      }
      if (data.status.state === 'stopped' && !data.enabled) {
        // Was disabled while starting
        qmdLoading.value = false
        return
      }
    } catch {
      // Network error, keep polling
    }
  }
  message.warning('QMD initialization timed out — check server logs')
  qmdLoading.value = false
}

async function reindexQMD() {
  reindexing.value = true
  try {
    await api.post('/settings/qmd/reindex')
    message.success('Reindex triggered')
  } catch {
    message.error('Reindex failed')
  } finally {
    reindexing.value = false
  }
}
</script>

<template>
  <PageLayout title="Settings" description="System configuration">
    <NTabs type="line" animated>
      <!-- General -->
      <NTabPane name="general" tab="General">
        <div class="settings-section">
          <h3 class="section-title">Theme</h3>
          <NSelect
            :value="themeStore.userPref"
            :options="themeOptions"
            style="width: 200px"
            @update:value="(v: any) => themeStore.setTheme(v)"
          />
        </div>

        <div class="settings-section">
          <p class="section-note">Model and provider defaults have been moved to the <strong>Providers</strong> page.</p>
        </div>

        <div class="settings-section">
          <h3 class="section-title">Memory Search</h3>
          <div class="qmd-toggle-row">
            <div class="qmd-label">
              <span>QMD Smart Search Engine</span>
              <NSwitch
                :value="qmdEnabled"
                :loading="qmdLoading"
                :disabled="qmdLoading"
                @update:value="toggleQMD"
              />
            </div>
            <p class="section-note">
              When enabled, memory search uses a local AI model for semantic matching
              with synonym understanding and contextual search. Requires ~1.2GB extra
              memory (low-memory devices auto-switch to on-demand mode).
              First-time setup will automatically download and install the required
              components (~80MB total), which may take 1-2 minutes.
              Disabling falls back to keyword search without restart.
            </p>
          </div>
          <div class="qmd-status-row" v-if="!qmdGpu.available && !qmdEnabled">
            <span class="status-dot warning"></span>
            <span class="status-text">No GPU detected — CPU mode will be slower</span>
          </div>
          <div class="qmd-status-row" v-if="qmdStatus">
            <span :class="['status-dot', qmdStatus.state]"></span>
            <span class="status-text">{{ statusLabel }}</span>
            <NButton
              v-if="qmdStatus.state === 'running'"
              size="small"
              tertiary
              @click="reindexQMD"
              :loading="reindexing"
            >
              Reindex
            </NButton>
          </div>
        </div>
      </NTabPane>

      <!-- Agent -->
      <NTabPane name="agent" tab="Agent">
        <div class="agent-editor">
          <!-- File selector bar -->
          <div class="editor-toolbar">
            <div class="file-tabs">
              <button
                v-for="opt in agentFileOptions"
                :key="opt.value"
                class="file-tab"
                :class="{ active: activeAgentFile === opt.value }"
                @click="activeAgentFile = opt.value"
              >
                {{ opt.label }}
              </button>
            </div>
            <NSpace :size="8">
              <NButton
                size="small"
                type="primary"
                :loading="savingAgent"
                @click="saveAgentFile"
              >
                Save
              </NButton>
            </NSpace>
          </div>

          <!-- MdEditorV3 -->
          <div class="editor-body">
            <MdEditor
              v-model="currentContent"
              :theme="themeStore.isDark ? 'dark' : 'light'"
              language="en-US"
              :preview="true"
              preview-theme="github"
              :style="{ height: '500px' }"
              :placeholder="`Edit ${activeAgentFile}...`"
              :toolbars="['bold', 'underline', 'italic', 'strikeThrough', '-', 'title', 'sub', 'sup', 'quote', 'unorderedList', 'orderedList', 'task', '-', 'codeRow', 'code', 'link', 'table', '-', 'revoke', 'next', '=', 'pageFullscreen', 'preview', 'catalog']"
            />
          </div>
        </div>

        <div class="settings-section" style="margin-top: var(--space-6)">
          <h3 class="section-title">MEMORY.md (Read Only)</h3>
          <div class="memory-viewer">
            <MdPreview
              :model-value="memoryContent || 'No memories yet.'"
              :theme="themeStore.isDark ? 'dark' : 'light'"
              preview-theme="github"
            />
          </div>
        </div>
      </NTabPane>

      <!-- Security -->
      <NTabPane name="security" tab="Security">
        <div class="settings-section">
          <h3 class="section-title">Change Password</h3>
          <NForm style="max-width: 400px">
            <NFormItem label="New Password">
              <NInput v-model:value="passwordForm.new_password" type="password" show-password-on="click" placeholder="At least 8 characters" />
            </NFormItem>
            <NFormItem label="Confirm Password">
              <NInput v-model:value="passwordForm.confirm_password" type="password" show-password-on="click" placeholder="Confirm" />
            </NFormItem>
            <NButton type="primary" :loading="savingPassword" @click="savePassword">Update Password</NButton>
          </NForm>
        </div>
      </NTabPane>

      <!-- Danger Zone -->
      <NTabPane name="danger" tab="Danger Zone">
        <NCard class="danger-card" :bordered="true">
          <div class="danger-item">
            <div>
              <h4 class="danger-title">Clear Agent Memory</h4>
              <p class="danger-desc">This will permanently erase all agent memories.</p>
            </div>
            <NButton type="error" ghost @click="showClearMemory = true">Clear Memory</NButton>
          </div>
        </NCard>
      </NTabPane>
    </NTabs>

    <ConfirmDialog
      v-model:show="showClearMemory"
      title="Clear Agent Memory"
      description="This will permanently delete all agent memories. This action cannot be undone."
      danger
      @confirm="handleClearMemory"
    />
    <ConfirmDialog
      v-model:show="showNoGpuConfirm"
      title="No GPU Detected"
      description="No GPU was detected on this server. QMD will run in CPU-only mode, which will be significantly slower for embedding and search operations. Are you sure you want to continue?"
      @confirm="confirmNoGpuStart"
    />
  </PageLayout>
</template>

<style scoped>
.settings-section {
  margin-bottom: var(--space-8);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-3);
}
.section-title {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}
.section-header .section-title {
  margin-bottom: 0;
}
.section-note {
  font-size: var(--text-sm);
  color: var(--text-muted);
}

/* Agent editor */
.agent-editor {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--surface);
}
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-3);
  background: var(--bg-muted);
  border-bottom: 1px solid var(--border);
}
.file-tabs {
  display: flex;
  gap: 2px;
}
.file-tab {
  background: none;
  border: none;
  padding: 4px 12px;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: var(--text-sm);
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all 150ms;
}
.file-tab:hover {
  color: var(--text-primary);
  background: var(--surface);
}
.file-tab.active {
  color: var(--text-primary);
  background: var(--surface);
  font-weight: 500;
  box-shadow: var(--shadow-sm);
}
.editor-body {
  min-height: 400px;
}
.editor-body :deep(.md-editor) {
  border: none;
  border-radius: 0;
}

.memory-viewer {
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  max-height: 300px;
  overflow-y: auto;
}
.danger-card {
  border-color: var(--accent-red) !important;
}
.danger-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}
.danger-title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-primary);
  margin: 0;
}
.danger-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 4px 0 0;
}

/* QMD */
.qmd-toggle-row {
  margin-bottom: var(--space-4);
}
.qmd-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
  font-weight: 500;
}
.qmd-status-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.status-dot.running {
  background: var(--accent-green, #22c55e);
}
.status-dot.stopped {
  background: var(--text-muted, #6b7280);
}
.status-dot.starting {
  background: var(--accent-yellow, #eab308);
  animation: pulse 1s infinite;
}
.status-dot.error {
  background: var(--accent-red, #ef4444);
}
.status-dot.warning {
  background: var(--accent-yellow, #eab308);
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.status-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
