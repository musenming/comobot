<script setup lang="ts">
import { ref, computed } from 'vue'
import { NModal, NInput, NButton, NSpace } from 'naive-ui'

const props = defineProps<{
  show: boolean
  title: string
  description?: string
  danger?: boolean
  confirmWord?: string
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'confirm'): void
}>()

const input = ref('')
const word = computed(() => props.confirmWord || 'DELETE')
const canConfirm = computed(() => !props.danger || input.value === word.value)

function handleConfirm() {
  if (canConfirm.value) {
    emit('confirm')
    emit('update:show', false)
    input.value = ''
  }
}

function handleCancel() {
  emit('update:show', false)
  input.value = ''
}
</script>

<template>
  <NModal :show="show" preset="card" :title="title" style="width: 420px;" @update:show="(v: boolean) => emit('update:show', v)">
    <p v-if="description" class="confirm-desc">{{ description }}</p>
    <div v-if="danger" class="confirm-input">
      <p class="confirm-hint">Type <strong>{{ word }}</strong> to confirm:</p>
      <NInput v-model:value="input" :placeholder="word" @keyup.enter="handleConfirm" />
    </div>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="handleCancel">Cancel</NButton>
        <NButton :type="danger ? 'error' : 'primary'" :disabled="!canConfirm" @click="handleConfirm">
          Confirm
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.confirm-desc {
  color: var(--text-secondary);
  font-size: var(--text-base);
  margin: 0 0 var(--space-4);
}
.confirm-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-2);
}
.confirm-input {
  margin-top: var(--space-4);
}
</style>
