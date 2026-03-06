<script setup lang="ts">
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, NButton, NSpace, useMessage } from 'naive-ui'
import SecretInput from './SecretInput.vue'
import api from '../api/client'

const props = defineProps<{
  show: boolean
  channelType: string | null
  fields: any[]
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'saved'): void
}>()

const message = useMessage()
const form = ref<Record<string, string>>({})
const testing = ref(false)
const saving = ref(false)

watch(() => [props.show, props.channelType], async () => {
  if (props.show && props.channelType) {
    try {
      const { data } = await api.get(`/channels/${props.channelType}/config`)
      form.value = data.config || {}
    } catch {
      form.value = {}
    }
  }
})

async function save() {
  if (!props.channelType) return
  saving.value = true
  try {
    await api.put(`/channels/${props.channelType}/config`, { config: form.value })
    message.success('Configuration saved')
    emit('saved')
    emit('update:show', false)
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to save')
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!props.channelType) return
  testing.value = true
  try {
    const { data } = await api.post(`/channels/${props.channelType}/test`)
    message.success(data.message || 'Test passed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Test failed')
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <NDrawer :show="show" :width="480" placement="right" @update:show="(v: boolean) => emit('update:show', v)">
    <NDrawerContent :title="`Configure ${channelType}`">
      <NForm label-placement="top">
        <NFormItem v-for="field in fields" :key="field.key" :label="field.label">
          <SecretInput
            v-if="field.type === 'secret'"
            :value="form[field.key] || ''"
            :placeholder="field.label"
            @update:value="(v: string) => form[field.key] = v"
          />
          <NSelect
            v-else-if="field.type === 'select'"
            :value="form[field.key] || field.default"
            :options="(field.options || []).map((o: string) => ({ label: o, value: o }))"
            @update:value="(v: string) => form[field.key] = v"
          />
          <NInput
            v-else
            :value="form[field.key] || ''"
            :placeholder="field.label"
            @update:value="(v: string) => form[field.key] = v"
          />
        </NFormItem>
      </NForm>

      <template #footer>
        <NSpace justify="space-between" style="width: 100%">
          <NButton :loading="testing" @click="test">Test Connection</NButton>
          <NSpace>
            <NButton @click="emit('update:show', false)">Cancel</NButton>
            <NButton type="primary" :loading="saving" @click="save">Save & Apply</NButton>
          </NSpace>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>
