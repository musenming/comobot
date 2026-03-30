<script setup lang="ts">
import { ref, watch, computed } from 'vue'
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
  mode: 'rest',
  api_key: '',
  api_base: '',
  app_key: '',
  access_key_id: '',
  access_key_secret: '',
  model: '',
  language: '',
})
const originalMaskedKey = ref('')
const originalMaskedAkId = ref('')
const originalMaskedAkSecret = ref('')

const providerOptions = [
  { label: 'Groq', value: 'groq' },
  { label: 'OpenAI', value: 'openai' },
  { label: 'Azure', value: 'azure' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'SiliconFlow', value: 'siliconflow' },
  { label: 'Ali NLS', value: 'ali_nls' },
  { label: 'Custom', value: 'custom' },
]

const modeOptions = [
  { label: 'REST API (OpenAI-compatible)', value: 'rest' },
  { label: 'Ali NLS (WebSocket)', value: 'ali_nls' },
]

const defaultApiBase: Record<string, string> = {
  groq: 'https://api.groq.com/openai/v1',
  openai: 'https://api.openai.com/v1',
  deepseek: 'https://api.deepseek.com/v1',
  siliconflow: 'https://api.siliconflow.cn/v1',
  ali_nls: 'wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1',
}

const defaultModel: Record<string, string> = {
  groq: 'whisper-large-v3',
  openai: 'whisper-1',
  deepseek: 'whisper-large-v3',
  siliconflow: 'FunAudioLLM/SenseVoiceSmall',
}

const defaultMode: Record<string, string> = {
  groq: 'rest',
  openai: 'rest',
  azure: 'rest',
  deepseek: 'rest',
  siliconflow: 'rest',
  ali_nls: 'ali_nls',
  custom: 'rest',
}

const isAliNls = computed(() => form.value.mode === 'ali_nls')

watch(() => props.show, async (v) => {
  if (v && props.editProvider) {
    form.value.provider = props.editProvider
    form.value.api_key = ''
    form.value.api_base = ''
    form.value.app_key = ''
    form.value.access_key_id = ''
    form.value.access_key_secret = ''
    form.value.model = ''
    form.value.language = ''
    form.value.mode = 'rest'
    loadingConfig.value = true
    try {
      const { data } = await api.get(`/asr/${props.editProvider}/config`)
      form.value.api_key = data.api_key || ''
      originalMaskedKey.value = form.value.api_key
      form.value.api_base = data.api_base || ''
      form.value.app_key = data.app_key || ''
      form.value.access_key_id = data.access_key_id || ''
      originalMaskedAkId.value = form.value.access_key_id
      form.value.access_key_secret = data.access_key_secret || ''
      originalMaskedAkSecret.value = form.value.access_key_secret
      form.value.model = data.model || ''
      form.value.language = data.language || ''
      form.value.mode = data.mode || 'rest'
    } catch {
      // Ignore
    } finally {
      loadingConfig.value = false
    }
  } else if (v) {
    form.value = {
      provider: '', mode: 'rest', api_key: '', api_base: '', app_key: '',
      access_key_id: '', access_key_secret: '', model: '', language: '',
    }
    originalMaskedKey.value = ''
    originalMaskedAkId.value = ''
    originalMaskedAkSecret.value = ''
  }
})

watch(() => form.value.provider, (v) => {
  // Auto-fill defaults when selecting a new provider (not editing)
  if (!props.editProvider && v) {
    if (defaultMode[v]) {
      form.value.mode = defaultMode[v]
    }
    if (!form.value.api_base && defaultApiBase[v]) {
      form.value.api_base = defaultApiBase[v]
    }
    if (!form.value.model && defaultModel[v]) {
      form.value.model = defaultModel[v]
    }
  }
})

async function save() {
  if (!form.value.provider) {
    message.warning(t('asr.selectProviderWarn'))
    return
  }
  saving.value = true
  try {
    await api.post('/asr', {
      provider: form.value.provider,
      mode: form.value.mode,
      api_key: form.value.api_key !== originalMaskedKey.value ? form.value.api_key : '',
      api_base: form.value.api_base || '',
      app_key: form.value.app_key || '',
      access_key_id: form.value.access_key_id !== originalMaskedAkId.value ? form.value.access_key_id : '',
      access_key_secret: form.value.access_key_secret !== originalMaskedAkSecret.value ? form.value.access_key_secret : '',
      model: form.value.model || '',
      language: form.value.language || null,
    })
    message.success(t('asr.saved'))
    emit('saved')
    emit('update:show', false)
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.failedSave'))
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!form.value.provider) return
  testing.value = true
  try {
    const { data } = await api.post(`/asr/${form.value.provider}/test`)
    message.success(data.detail || t('asr.testPassed'))
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.testFailed'))
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <NDrawer :show="show" :width="480" placement="right" @update:show="(v: boolean) => emit('update:show', v)">
    <NDrawerContent :title="editProvider ? t('asr.editProvider', { name: editProvider }) : t('asr.addProviderTitle')">
      <NForm label-placement="top">
        <NFormItem :label="t('asr.provider')">
          <NSelect
            v-model:value="form.provider"
            :options="providerOptions"
            :disabled="!!editProvider"
            :placeholder="t('asr.selectProvider')"
          />
        </NFormItem>
        <NFormItem :label="t('asr.mode')">
          <NSelect
            v-model:value="form.mode"
            :options="modeOptions"
          />
        </NFormItem>

        <!-- REST mode fields -->
        <template v-if="!isAliNls">
          <NFormItem :label="t('asr.apiKey')">
            <SecretInput
              :value="form.api_key"
              :placeholder="t('asr.enterApiKey')"
              @update:value="(v: string) => form.api_key = v"
            />
          </NFormItem>
          <NFormItem :label="t('asr.apiBaseUrl')">
            <NInput
              v-model:value="form.api_base"
              placeholder="https://api.groq.com/openai/v1"
            />
          </NFormItem>
          <NFormItem :label="t('asr.model')">
            <NInput
              v-model:value="form.model"
              placeholder="whisper-large-v3"
            />
          </NFormItem>
        </template>

        <!-- Ali NLS mode fields -->
        <template v-else>
          <NFormItem label="AccessKey ID">
            <SecretInput
              :value="form.access_key_id"
              :placeholder="t('asr.enterAccessKeyId')"
              @update:value="(v: string) => form.access_key_id = v"
            />
          </NFormItem>
          <NFormItem label="AccessKey Secret">
            <SecretInput
              :value="form.access_key_secret"
              :placeholder="t('asr.enterAccessKeySecret')"
              @update:value="(v: string) => form.access_key_secret = v"
            />
          </NFormItem>
          <NFormItem label="AppKey">
            <NInput
              v-model:value="form.app_key"
              :placeholder="t('asr.enterAppKey')"
            />
          </NFormItem>
          <NFormItem :label="t('asr.wsUrl')">
            <NInput
              v-model:value="form.api_base"
              placeholder="wss://nls-gateway-cn-shanghai.aliyuncs.com/ws/v1"
            />
          </NFormItem>
          <NFormItem :label="'Token (' + t('asr.optional') + ')'">
            <SecretInput
              :value="form.api_key"
              :placeholder="t('asr.enterToken')"
              @update:value="(v: string) => form.api_key = v"
            />
          </NFormItem>
        </template>

        <NFormItem :label="t('asr.language')">
          <NInput
            v-model:value="form.language"
            :placeholder="t('asr.languagePlaceholder')"
          />
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
