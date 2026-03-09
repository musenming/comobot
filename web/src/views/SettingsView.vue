<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

// Agent files
const soulContent = ref('')
const userContent = ref('')
const memoryContent = ref('')
const savingAgent = ref(false)
const previewSoul = ref(false)
const previewUser = ref(false)

// Defaults
const defaultsForm = ref({ model: '', provider: 'auto' })
const savingDefaults = ref(false)
const providerOptions = ref<{ label: string; value: string }[]>([{ label: 'Auto', value: 'auto' }])

// Danger zone
const showClearMemory = ref(false)

const themeOptions = [
  { label: 'Dark', value: 'dark' },
  { label: 'Light', value: 'light' },
  { label: 'System', value: 'system' },
]

onMounted(async () => {
  try {
    const [soul, user, memory, defaults, providers] = await Promise.all([
      api.get('/settings/soul'),
      api.get('/settings/user'),
      api.get('/settings/memory'),
      api.get('/settings/defaults').catch(() => null),
      api.get('/providers').catch(() => null),
    ])
    soulContent.value = soul.data.content || ''
    userContent.value = user.data.content || ''
    memoryContent.value = memory.data.content || ''
    if (defaults?.data) {
      defaultsForm.value.model = defaults.data.model || ''
      defaultsForm.value.provider = defaults.data.provider || 'auto'
    }
    if (providers?.data) {
      const opts = [{ label: 'Auto', value: 'auto' }]
      for (const p of providers.data) {
        opts.push({ label: p.provider, value: p.provider })
      }
      providerOptions.value = opts
    }
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

async function saveSoul() {
  savingAgent.value = true
  try {
    await api.put('/settings/soul', { content: soulContent.value })
    message.success('SOUL.md saved')
  } catch {
    message.error('Failed to save')
  } finally {
    savingAgent.value = false
  }
}

async function saveUser() {
  savingAgent.value = true
  try {
    await api.put('/settings/user', { content: userContent.value })
    message.success('USER.md saved')
  } catch {
    message.error('Failed to save')
  } finally {
    savingAgent.value = false
  }
}

async function saveDefaults() {
  savingDefaults.value = true
  try {
    await api.put('/settings/defaults', defaultsForm.value)
    message.success('Defaults saved')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to save defaults')
  } finally {
    savingDefaults.value = false
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
          <div class="section-header">
            <h3 class="section-title">Defaults</h3>
            <NButton size="small" type="primary" :loading="savingDefaults" @click="saveDefaults">Save</NButton>
          </div>
          <NForm label-placement="top" style="max-width: 400px">
            <NFormItem label="Model">
              <NInput v-model:value="defaultsForm.model" placeholder="e.g. anthropic/claude-opus-4-5" />
            </NFormItem>
            <NFormItem label="Provider">
              <NSelect v-model:value="defaultsForm.provider" :options="providerOptions" />
            </NFormItem>
          </NForm>
        </div>
      </NTabPane>

      <!-- Agent -->
      <NTabPane name="agent" tab="Agent">
        <div class="settings-section">
          <div class="section-header">
            <h3 class="section-title">SOUL.md</h3>
            <NSpace>
              <NButton size="small" quaternary @click="previewSoul = !previewSoul">
                {{ previewSoul ? 'Edit' : 'Preview' }}
              </NButton>
              <NButton size="small" type="primary" :loading="savingAgent" @click="saveSoul">Save</NButton>
            </NSpace>
          </div>
          <MarkdownRenderer v-if="previewSoul" :content="soulContent" />
          <NInput v-else v-model:value="soulContent" type="textarea" :rows="12" placeholder="Agent personality..." />
        </div>

        <div class="settings-section">
          <div class="section-header">
            <h3 class="section-title">USER.md</h3>
            <NSpace>
              <NButton size="small" quaternary @click="previewUser = !previewUser">
                {{ previewUser ? 'Edit' : 'Preview' }}
              </NButton>
              <NButton size="small" type="primary" :loading="savingAgent" @click="saveUser">Save</NButton>
            </NSpace>
          </div>
          <MarkdownRenderer v-if="previewUser" :content="userContent" />
          <NInput v-else v-model:value="userContent" type="textarea" :rows="8" placeholder="User info..." />
        </div>

        <div class="settings-section">
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
