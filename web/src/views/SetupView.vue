<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, NSelect, NSpace, useMessage } from 'naive-ui'
import SecretInput from '../components/SecretInput.vue'
import api from '../api/client'

const router = useRouter()
const message = useMessage()
const currentStep = ref(1)
const loading = ref(false)
const validating = ref(false)
const validateStatus = ref<'idle' | 'success' | 'error'>('idle')
const validateMessage = ref('')
const providerOptions = ref<Array<{ label: string; value: string; recommended: boolean; needsKey: boolean }>>([])

const form = ref({
  admin_password: '',
  admin_password_confirm: '',
  provider: null as string | null,
  api_key: '',
  telegram_token: '',
  telegram_mode: 'polling',
  assistant_name: 'Comobot',
  language: 'zh',
})

onMounted(async () => {
  try {
    const { data } = await api.get('/setup/providers')
    providerOptions.value = data.map((p: any) => ({
      label: p.name,
      value: p.id,
      recommended: p.recommended,
      needs_key: p.needs_key,
    }))
  } catch {
    // fallback static list
    providerOptions.value = [
      { label: 'OpenRouter（推荐）', value: 'openrouter', recommended: true, needsKey: true },
      { label: 'OpenAI', value: 'openai', recommended: false, needsKey: true },
      { label: 'Anthropic (Claude)', value: 'anthropic', recommended: false, needsKey: true },
      { label: 'DeepSeek', value: 'deepseek', recommended: false, needsKey: true },
      { label: 'Google Gemini', value: 'gemini', recommended: false, needsKey: true },
      { label: '本地模型（Ollama）', value: 'ollama', recommended: false, needsKey: false },
    ]
  }
})

const selectOptions = computed(() =>
  providerOptions.value.map((p) => ({
    label: p.label + (p.recommended ? ' ⭐' : ''),
    value: p.value,
  }))
)

const currentProvider = computed(() =>
  providerOptions.value.find((p) => p.value === form.value.provider)
)

const needsKey = computed(() => {
  if (!currentProvider.value) return false
  return (currentProvider.value as any).needs_key ?? (currentProvider.value as any).needsKey ?? true
})

const languageOptions = [
  { label: '中文（简体）', value: 'zh' },
  { label: 'English', value: 'en' },
]

const passwordStrength = computed(() => {
  const p = form.value.admin_password
  if (!p) return 0
  let s = 0
  if (p.length >= 8) s++
  if (/[A-Z]/.test(p)) s++
  if (/[0-9]/.test(p)) s++
  if (/[^A-Za-z0-9]/.test(p)) s++
  return s
})

const strengthLabel = computed(() => {
  return ['', 'Weak', 'Fair', 'Good', 'Strong'][passwordStrength.value] || ''
})

const strengthColor = computed(() => {
  return ['', 'var(--accent-red)', 'var(--accent-yellow)', 'var(--accent-blue)', 'var(--accent-green)'][passwordStrength.value] || ''
})

const steps = [
  { num: 1, label: 'Admin' },
  { num: 2, label: 'LLM' },
  { num: 3, label: 'Telegram' },
  { num: 4, label: 'Done' },
]

const accessUrl = computed(() => `http://localhost:${window.location.port || 18790}`)

function nextStep() {
  if (currentStep.value === 1) {
    if (form.value.admin_password.length < 8) {
      message.warning('Password must be at least 8 characters')
      return
    }
    if (form.value.admin_password !== form.value.admin_password_confirm) {
      message.warning('Passwords do not match')
      return
    }
  }
  currentStep.value++
}

function prevStep() {
  currentStep.value--
}

function onProviderChange() {
  validateStatus.value = 'idle'
  validateMessage.value = ''
}

async function validateKey() {
  if (!form.value.provider || !form.value.api_key) return
  validating.value = true
  validateStatus.value = 'idle'
  validateMessage.value = ''
  try {
    const { data } = await api.post('/setup/validate-key', {
      provider: form.value.provider,
      api_key: form.value.api_key,
    })
    validateStatus.value = data.valid ? 'success' : 'error'
    validateMessage.value = data.message
  } catch (e: any) {
    validateStatus.value = 'error'
    validateMessage.value = e.response?.data?.detail || '验证请求失败'
  } finally {
    validating.value = false
  }
}

async function finishSetup() {
  loading.value = true
  try {
    await api.post('/setup', {
      admin_password: form.value.admin_password,
      provider: form.value.provider,
      api_key: form.value.api_key || undefined,
      telegram_token: form.value.telegram_token || undefined,
      telegram_mode: form.value.telegram_mode,
      assistant_name: form.value.assistant_name || undefined,
      language: form.value.language || undefined,
    })
    message.success('Setup complete!')
    router.push('/login')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Setup failed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="setup-container">
    <div class="setup-card">
      <!-- Step Progress -->
      <div class="step-progress">
        <template v-for="(step, idx) in steps" :key="step.num">
          <div
            class="step-circle"
            :class="{
              active: currentStep === step.num,
              completed: currentStep > step.num,
            }"
          >
            <span v-if="currentStep > step.num" class="step-check">✓</span>
            <span v-else>{{ step.num }}</span>
          </div>
          <div v-if="idx < steps.length - 1" class="step-line" :class="{ completed: currentStep > step.num }" />
        </template>
      </div>
      <div class="step-labels">
        <span v-for="step in steps" :key="step.num" class="step-label" :class="{ active: currentStep === step.num }">
          {{ step.label }}
        </span>
      </div>

      <!-- Step 1: Password -->
      <Transition name="slide" mode="out-in">
        <NForm v-if="currentStep === 1" key="step1">
          <NFormItem label="Admin Password">
            <NInput v-model:value="form.admin_password" type="password" show-password-on="click" placeholder="At least 8 characters" size="large" />
          </NFormItem>
          <div v-if="form.admin_password" class="strength-bar">
            <div class="strength-track">
              <div
                class="strength-fill"
                :style="{ width: `${passwordStrength * 25}%`, background: strengthColor }"
              />
            </div>
            <span class="strength-label" :style="{ color: strengthColor }">{{ strengthLabel }}</span>
          </div>
          <NFormItem label="Confirm Password">
            <NInput v-model:value="form.admin_password_confirm" type="password" show-password-on="click" placeholder="Confirm" size="large" />
          </NFormItem>
          <NSpace justify="end">
            <NButton type="primary" size="large" @click="nextStep">Next</NButton>
          </NSpace>
        </NForm>

        <!-- Step 2: Provider -->
        <NForm v-else-if="currentStep === 2" key="step2">
          <NFormItem label="AI 提供商">
            <NSelect
              v-model:value="form.provider"
              :options="selectOptions"
              placeholder="选择 AI 提供商"
              clearable
              size="large"
              @update:value="onProviderChange"
            />
          </NFormItem>
          <div v-if="currentProvider?.recommended" class="provider-tip">
            <span class="tip-badge">⭐ 推荐</span>
            OpenRouter 支持几乎所有主流模型，新手首选
          </div>
          <NFormItem v-if="form.provider && needsKey" label="API Key">
            <div class="key-row">
              <SecretInput
                :value="form.api_key"
                placeholder="粘贴 API Key"
                @update:value="(v: string) => { form.api_key = v; validateStatus = 'idle' }"
                style="flex: 1"
              />
              <NButton
                :loading="validating"
                :disabled="!form.api_key"
                size="large"
                style="margin-left: 8px; flex-shrink: 0"
                @click="validateKey"
              >
                验证
              </NButton>
            </div>
          </NFormItem>
          <div v-if="validateStatus !== 'idle'" class="validate-result" :class="validateStatus">
            <span v-if="validateStatus === 'success'">✅ {{ validateMessage }}</span>
            <span v-else>❌ {{ validateMessage }}</span>
          </div>
          <NSpace justify="space-between" style="margin-top: 16px">
            <NButton size="large" @click="prevStep">Back</NButton>
            <NButton type="primary" size="large" @click="nextStep">Next</NButton>
          </NSpace>
        </NForm>

        <!-- Step 3: Telegram -->
        <NForm v-else-if="currentStep === 3" key="step3">
          <NFormItem label="Telegram Bot Token（可选）">
            <SecretInput
              :value="form.telegram_token"
              placeholder="123456:ABC-DEF..."
              @update:value="(v: string) => form.telegram_token = v"
            />
          </NFormItem>
          <NSpace justify="space-between">
            <NButton size="large" @click="prevStep">Back</NButton>
            <NButton type="primary" size="large" @click="nextStep">Next</NButton>
          </NSpace>
        </NForm>

        <!-- Step 4: Complete -->
        <NForm v-else key="step4">
          <NFormItem label="助手名称">
            <NInput v-model:value="form.assistant_name" placeholder="Comobot" size="large" />
          </NFormItem>
          <NFormItem label="界面语言">
            <NSelect v-model:value="form.language" :options="languageOptions" size="large" />
          </NFormItem>
          <div class="access-url">
            <span class="url-label">完成后访问：</span>
            <span class="url-value">{{ accessUrl }}</span>
          </div>
          <NSpace justify="space-between" style="margin-top: 24px">
            <NButton size="large" @click="prevStep">Back</NButton>
            <NButton type="primary" size="large" :loading="loading" @click="finishSetup">
              开始使用
            </NButton>
          </NSpace>
        </NForm>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.setup-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-base);
}
.setup-card {
  width: 560px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--space-10);
  box-shadow: 0 0 0 1px var(--border), var(--shadow-lg);
}

/* Step Progress */
.step-progress {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: var(--space-2);
}
.step-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-muted);
  flex-shrink: 0;
  transition: all 200ms var(--ease-default);
}
.step-circle.active {
  border-color: var(--text-primary);
  color: var(--text-primary);
  background: var(--bg-muted);
}
.step-circle.completed {
  border-color: var(--accent-green);
  color: var(--accent-green);
  background: transparent;
}
.step-check {
  font-size: 14px;
}
.step-line {
  width: 48px;
  height: 2px;
  background: var(--border);
  transition: background 200ms;
}
.step-line.completed {
  background: var(--accent-green);
}
.step-labels {
  display: flex;
  justify-content: space-between;
  padding: 0 12px;
  margin-bottom: var(--space-8);
}
.step-label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-align: center;
  width: 60px;
}
.step-label.active {
  color: var(--text-primary);
}

/* Strength Bar */
.strength-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.strength-track {
  flex: 1;
  height: 4px;
  background: var(--bg-muted);
  border-radius: 2px;
  overflow: hidden;
}
.strength-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 200ms, background 200ms;
}
.strength-label {
  font-size: var(--text-xs);
  font-weight: 500;
  min-width: 40px;
}

/* Provider tip */
.provider-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--space-4);
}
.tip-badge {
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  color: var(--text-primary);
  white-space: nowrap;
}

/* Key row */
.key-row {
  display: flex;
  align-items: center;
  width: 100%;
}

/* Validate result */
.validate-result {
  font-size: var(--text-sm);
  padding: 8px 12px;
  border-radius: var(--radius);
  margin-bottom: var(--space-4);
}
.validate-result.success {
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  color: var(--accent-green);
  border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent);
}
.validate-result.error {
  background: color-mix(in srgb, var(--accent-red) 10%, transparent);
  color: var(--accent-red);
  border: 1px solid color-mix(in srgb, var(--accent-red) 30%, transparent);
}

/* Access URL */
.access-url {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: var(--bg-muted);
  border-radius: var(--radius);
  font-size: var(--text-sm);
  margin-top: 8px;
}
.url-label {
  color: var(--text-muted);
  white-space: nowrap;
}
.url-value {
  color: var(--text-primary);
  font-weight: 500;
}

/* Slide transition */
.slide-enter-active,
.slide-leave-active {
  transition: transform 300ms var(--ease-default), opacity 300ms var(--ease-default);
}
.slide-enter-from {
  transform: translateX(20px);
  opacity: 0;
}
.slide-leave-to {
  transform: translateX(-20px);
  opacity: 0;
}
</style>
