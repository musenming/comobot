<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton } from 'naive-ui'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const errorMsg = ref('')
const form = ref({ username: 'admin', password: '' })

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    await auth.login(form.value.username, form.value.password)
    router.push('/')
  } catch {
    errorMsg.value = 'Invalid username or password'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-mark">●</div>
        <h1 class="logo-text">comobot</h1>
        <p class="logo-sub">Intelligent Agent Platform</p>
      </div>

      <NForm @submit.prevent="handleLogin">
        <NFormItem label="Username" :validation-status="errorMsg ? 'error' : undefined">
          <NInput
            v-model:value="form.username"
            placeholder="admin"
            size="large"
          />
        </NFormItem>
        <NFormItem label="Password" :validation-status="errorMsg ? 'error' : undefined" :feedback="errorMsg">
          <NInput
            v-model:value="form.password"
            type="password"
            show-password-on="click"
            placeholder="Password"
            size="large"
            @keyup.enter="handleLogin"
          />
        </NFormItem>
        <NButton
          type="primary"
          :loading="loading"
          block
          size="large"
          @click="handleLogin"
          style="margin-top: 8px"
        >
          Sign In
        </NButton>
      </NForm>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-base);
}
.login-card {
  width: 400px;
  max-width: 92vw;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  padding: var(--space-10);
  box-shadow: 0 0 0 1px var(--border), var(--shadow-lg);
}
.login-header {
  text-align: center;
  margin-bottom: var(--space-8);
}
.logo-mark {
  font-size: 28px;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}
.logo-text {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: 0.5px;
}
.logo-sub {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--space-1) 0 0;
  font-weight: 300;
}
</style>
