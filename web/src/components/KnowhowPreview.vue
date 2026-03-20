<script setup lang="ts">
import { ref, watch } from 'vue'
import { NModal, NForm, NFormItem, NInput, NDynamicTags, NButton, NSpin } from 'naive-ui'
import api from '../api/client'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  sessionKey: string
  messageIds: number[]
  show: boolean
}>()
const emit = defineEmits<{ saved: []; 'update:show': [v: boolean] }>()

const visible = ref(false)
const preview = ref<any>(null)
const loading = ref(false)
const saving = ref(false)

watch(() => props.show, async (v) => {
  visible.value = v
  if (v && props.messageIds.length > 0) {
    loading.value = true
    try {
      const { data } = await api.post('/knowhow/extract', {
        session_key: props.sessionKey,
        message_ids: props.messageIds,
      })
      preview.value = data.preview
    } catch (e) {
      preview.value = { title: 'Extraction failed', goal: '', steps: [], tags: [] }
    } finally {
      loading.value = false
    }
  }
})

watch(visible, (v) => {
  if (!v) emit('update:show', false)
})

async function save() {
  if (!preview.value) return
  saving.value = true
  try {
    await api.post('/knowhow', {
      preview: preview.value,
      session_key: props.sessionKey,
      message_ids: props.messageIds,
    })
    emit('saved')
    visible.value = false
  } catch {
    // error handling
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-modal v-model:show="visible" preset="card" :title="t('knowhow.preview')" style="width: 600px; max-width: 90vw">
    <n-spin :show="loading">
      <n-form v-if="preview" label-placement="top">
        <n-form-item :label="t('knowhow.titleField')">
          <n-input v-model:value="preview.title" />
        </n-form-item>
        <n-form-item :label="t('knowhow.goal')">
          <n-input v-model:value="preview.goal" type="textarea" :rows="2" />
        </n-form-item>
        <n-form-item :label="t('knowhow.keySteps')">
          <ol class="steps-list">
            <li v-for="(step, i) in preview.steps" :key="i">{{ step }}</li>
          </ol>
        </n-form-item>
        <n-form-item v-if="preview.outcome" :label="t('knowhow.outcome')">
          <span>{{ preview.outcome }}</span>
        </n-form-item>
        <n-form-item :label="t('knowhow.tags')">
          <n-dynamic-tags v-model:value="preview.tags" />
        </n-form-item>
      </n-form>
      <div v-else-if="!loading" style="padding: 20px; text-align: center; color: var(--text-muted)">
        {{ t('knowhow.noPreview') }}
      </div>
    </n-spin>
    <template #action>
      <n-button type="primary" :loading="saving" :disabled="!preview" @click="save">
        {{ t('knowhow.confirmSave') }}
      </n-button>
    </template>
  </n-modal>
</template>

<style scoped>
.steps-list {
  margin: 0;
  padding-left: 20px;
}
.steps-list li {
  margin-bottom: 4px;
  font-size: var(--text-sm);
}
</style>
