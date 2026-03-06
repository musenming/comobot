<script setup lang="ts">
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NForm, NFormItem, NSelect, NButton, NSpace, useMessage } from 'naive-ui'
import SecretInput from './SecretInput.vue'
import api from '../api/client'

const props = defineProps<{
  show: boolean
  editProvider?: string | null
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'saved'): void
}>()

const message = useMessage()
const saving = ref(false)
const testing = ref(false)

const form = ref({
  provider: '',
  api_key: '',
})

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

watch(() => props.show, (v) => {
  if (v && props.editProvider) {
    form.value.provider = props.editProvider
    form.value.api_key = ''
  } else if (v) {
    form.value = { provider: '', api_key: '' }
  }
})

async function save() {
  if (!form.value.provider) {
    message.warning('Please select a provider')
    return
  }
  saving.value = true
  try {
    await api.post('/providers', {
      provider: form.value.provider,
      key_name: 'api_key',
      value: form.value.api_key,
    })
    message.success('Provider saved')
    emit('saved')
    emit('update:show', false)
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to save')
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!form.value.provider) return
  testing.value = true
  try {
    const { data } = await api.post(`/providers/${form.value.provider}/test`)
    message.success(`Test passed - ${data.key_prefix} (${data.latency_ms}ms)`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Test failed')
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <NDrawer :show="show" :width="480" placement="right" @update:show="(v: boolean) => emit('update:show', v)">
    <NDrawerContent :title="editProvider ? `Edit ${editProvider}` : 'Add Provider'">
      <NForm label-placement="top">
        <NFormItem label="Provider">
          <NSelect
            v-model:value="form.provider"
            :options="providerOptions"
            :disabled="!!editProvider"
            placeholder="Select provider"
          />
        </NFormItem>
        <NFormItem label="API Key">
          <SecretInput
            :value="form.api_key"
            placeholder="Enter API key"
            @update:value="(v: string) => form.api_key = v"
          />
        </NFormItem>
      </NForm>

      <template #footer>
        <NSpace justify="space-between" style="width: 100%">
          <NButton :loading="testing" @click="test">Test Connection</NButton>
          <NSpace>
            <NButton @click="emit('update:show', false)">Cancel</NButton>
            <NButton type="primary" :loading="saving" @click="save">Save</NButton>
          </NSpace>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
