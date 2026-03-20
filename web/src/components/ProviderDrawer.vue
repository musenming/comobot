<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  NDrawer, NDrawerContent, NForm, NFormItem, NSelect, NButton, NSpace,
  NInput, useMessage,
} from 'naive-ui'
import SecretInput from './SecretInput.vue'
import api, { restartGateway } from '../api/client'
import { useI18n } from '../composables/useI18n'

const props = defineProps<{
  show: boolean
  editProvider?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'saved'): void
}>()

const { t } = useI18n()
const message = useMessage()
const saving = ref(false)
const testing = ref(false)
const loadingConfig = ref(false)

const form = ref({
  provider: '',
  api_key: '',
  api_base: '',
  extra_headers: [] as { key: string; value: string }[],
})
const originalMaskedKey = ref('')

const providerOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic (Claude)', value: 'anthropic' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'DashScope', value: 'dashscope' },
  { label: 'Gemini', value: 'gemini' },
  { label: 'Moonshot', value: 'moonshot' },
  { label: 'Zhipu AI', value: 'zhipu' },
  { label: 'MiniMax', value: 'minimax' },
  { label: 'OpenRouter', value: 'openrouter' },
  { label: 'Groq', value: 'groq' },
  { label: 'vLLM', value: 'vllm' },
  { label: 'AiHubMix', value: 'aihubmix' },
  { label: 'SiliconFlow', value: 'siliconflow' },
  { label: 'VolcEngine', value: 'volcengine' },
  { label: 'OpenAI Codex', value: 'openai_codex' },
  { label: 'GitHub Copilot', value: 'github_copilot' },
  { label: 'Custom', value: 'custom' },
]

watch(() => props.show, async (v) => {
  if (v && props.editProvider) {
    form.value.provider = props.editProvider
    form.value.api_key = ''
    form.value.api_base = ''
    form.value.extra_headers = []
    // Load saved config
    loadingConfig.value = true
    try {
      const { data } = await api.get(`/providers/${props.editProvider}/config`)
      form.value.api_key = data.api_key || ''
      originalMaskedKey.value = form.value.api_key
      form.value.api_base = data.api_base || ''
      const headers = data.extra_headers || {}
      form.value.extra_headers = Object.entries(headers).map(([key, value]) => ({
        key,
        value: value as string,
      }))
    } catch {
      // Ignore — may not have config yet
    } finally {
      loadingConfig.value = false
    }
  } else if (v) {
    form.value = { provider: '', api_key: '', api_base: '', extra_headers: [] }
    originalMaskedKey.value = ''
  }
})

function addHeader() {
  form.value.extra_headers.push({ key: '', value: '' })
}

function removeHeader(index: number) {
  form.value.extra_headers.splice(index, 1)
}

async function save() {
  if (!form.value.provider) {
    message.warning(t('providers.selectProviderWarn'))
    return
  }
  saving.value = true
  try {
    // Build extra_headers dict from array
    const extraHeaders: Record<string, string> = {}
    for (const h of form.value.extra_headers) {
      if (h.key.trim()) {
        extraHeaders[h.key.trim()] = h.value
      }
    }
    // Only send api_key if user actually changed it (not the masked placeholder)
    const apiKeyChanged = form.value.api_key !== originalMaskedKey.value
    await api.post('/providers', {
      provider: form.value.provider,
      key_name: 'api_key',
      value: apiKeyChanged ? form.value.api_key : '',
      api_base: form.value.api_base || null,
      extra_headers: Object.keys(extraHeaders).length > 0 ? extraHeaders : null,
    })
    message.success(t('providers.saved'))
    emit('saved')
    emit('update:show', false)
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('providers.failedSaveProvider'))
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!form.value.provider) return
  testing.value = true
  try {
    const { data } = await api.post(`/providers/${form.value.provider}/test`)
    message.success(`${t('providers.testPassed')} ${data.key_prefix} (${data.latency_ms}ms)`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('providers.testFailed'))
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <NDrawer :show="show" :width="480" placement="right" @update:show="(v: boolean) => emit('update:show', v)">
    <NDrawerContent :title="editProvider ? t('providers.editProvider', { name: editProvider }) : t('providers.addProviderTitle')">
      <NForm label-placement="top">
        <NFormItem :label="t('providers.provider')">
          <NSelect
            v-model:value="form.provider"
            :options="providerOptions"
            :disabled="!!editProvider"
            :placeholder="t('providers.selectProvider')"
          />
        </NFormItem>
        <NFormItem :label="t('providers.apiKey')">
          <SecretInput
            :value="form.api_key"
            :placeholder="t('providers.enterApiKey')"
            @update:value="(v: string) => form.api_key = v"
          />
        </NFormItem>
        <NFormItem :label="t('providers.apiBaseUrl')">
          <NInput
            v-model:value="form.api_base"
            placeholder="https://api.example.com/v1"
          />
        </NFormItem>
        <NFormItem :label="t('providers.extraHeaders')">
          <div style="width: 100%">
            <div
              v-for="(header, index) in form.extra_headers"
              :key="index"
              style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;"
            >
              <NInput
                v-model:value="header.key"
                :placeholder="t('providers.headerName')"
                style="flex: 1"
              />
              <NInput
                v-model:value="header.value"
                :placeholder="t('providers.headerValue')"
                style="flex: 1"
              />
              <NButton quaternary size="small" @click="removeHeader(index)">
                ✕
              </NButton>
            </div>
            <NButton size="small" dashed @click="addHeader">{{ t('providers.addHeader') }}</NButton>
          </div>
        </NFormItem>
      </NForm>

      <template #footer>
        <NSpace justify="space-between" style="width: 100%">
          <NButton :loading="testing" @click="test">{{ t('channels.testConnection') }}</NButton>
          <NSpace>
            <NButton @click="emit('update:show', false)">{{ t('common.cancel') }}</NButton>
            <NButton type="primary" :loading="saving" @click="save">{{ t('common.save') }}</NButton>
          </NSpace>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
