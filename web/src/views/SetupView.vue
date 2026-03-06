<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, NSelect, NSpace, useMessage } from 'naive-ui'
import SecretInput from '../components/SecretInput.vue'
import api from '../api/client'

const router = useRouter()
const message = useMessage()
const currentStep = ref(1)
const loading = ref(false)

const form = ref({
  admin_password: '',
  admin_password_confirm: '',
  provider: null as string | null,
  api_key: '',
  telegram_token: '',
  telegram_mode: 'polling',
})

const providerOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic (Claude)', value: 'anthropic' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'DashScope', value: 'dashscope' },
  { label: 'Gemini', value: 'gemini' },
  { label: 'Moonshot (Kimi)', value: 'moonshot' },
  { label: 'Zhipu AI', value: 'zhipu' },
  { label: 'MiniMax', value: 'minimax' },
  { label: 'Local (Ollama)', value: 'ollama' },
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

async function finishSetup() {
  loading.value = true
  try {
    await api.post('/setup', {
      admin_password: form.value.admin_password,
      provider: form.value.provider,
      api_key: form.value.api_key || undefined,
      telegram_token: form.value.telegram_token || undefined,
      telegram_mode: form.value.telegram_mode,
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
          <NFormItem label="Provider">
            <NSelect v-model:value="form.provider" :options="providerOptions" placeholder="Select provider" clearable size="large" />
          </NFormItem>
          <NFormItem label="API Key" v-if="form.provider && form.provider !== 'ollama'">
            <SecretInput
              :value="form.api_key"
              placeholder="API Key"
              @update:value="(v: string) => form.api_key = v"
            />
          </NFormItem>
          <NSpace justify="space-between">
            <NButton size="large" @click="prevStep">Back</NButton>
            <NButton type="primary" size="large" @click="nextStep">Next</NButton>
          </NSpace>
        </NForm>

        <!-- Step 3: Telegram -->
        <NForm v-else-if="currentStep === 3" key="step3">
          <NFormItem label="Telegram Bot Token (optional)">
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
        <div v-else key="step4" class="complete-step">
          <div class="check-circle">✓</div>
          <h2 class="complete-title">Ready to go!</h2>
          <p class="complete-desc">Your comobot instance is configured and ready.</p>
          <NSpace justify="center" style="margin-top: 24px;">
            <NButton size="large" @click="prevStep">Back</NButton>
            <NButton type="primary" size="large" :loading="loading" @click="finishSetup">
              Start Agent
            </NButton>
          </NSpace>
        </div>
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

/* Complete */
.complete-step {
  text-align: center;
  padding: var(--space-6) 0;
}
.check-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--accent-green);
  color: white;
  font-size: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--space-6);
}
.complete-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 var(--space-2);
}
.complete-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
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
