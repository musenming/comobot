<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NButton, NInput, NForm, NFormItem, NTabs, NTabPane, NSelect, NSpace, NCard, useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import { useThemeStore } from '../stores/theme'
import api from '../api/client'

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
const agentPreview = ref(false)
const savingAgent = ref(false)

// Memory (read only)
const memoryContent = ref('')

// Danger zone
const showClearMemory = ref(false)

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
  try {
    await api.put(endpoint, { content: currentContent.value })
    message.success(`${activeAgentFile.value} saved`)
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
                @click="activeAgentFile = opt.value; agentPreview = false"
              >
                {{ opt.label }}
              </button>
            </div>
            <NSpace :size="8">
              <NButton
                size="small"
                quaternary
                @click="agentPreview = !agentPreview"
              >
                {{ agentPreview ? 'Edit' : 'Preview' }}
              </NButton>
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

          <!-- Editor / Preview -->
          <div class="editor-body">
            <div v-if="agentPreview" class="md-preview">
              <MarkdownRenderer :content="currentContent || '*Empty file*'" />
            </div>
            <NInput
              v-else
              v-model:value="currentContent"
              type="textarea"
              :rows="18"
              :placeholder="`Edit ${activeAgentFile}...`"
              class="editor-textarea"
            />
          </div>
        </div>

        <div class="settings-section" style="margin-top: var(--space-6)">
          <h3 class="section-title">MEMORY.md (Read Only)</h3>
          <div class="memory-viewer">
            <MarkdownRenderer :content="memoryContent || 'No memories yet.'" />
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
.editor-body :deep(.n-input) {
  border: none;
  border-radius: 0;
}
.editor-body :deep(.n-input__border),
.editor-body :deep(.n-input__state-border) {
  display: none;
}
.editor-textarea :deep(textarea) {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace !important;
  font-size: 13px !important;
  line-height: 1.6 !important;
}
.md-preview {
  padding: var(--space-4) var(--space-6);
  min-height: 400px;
  overflow-y: auto;
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
</style>
