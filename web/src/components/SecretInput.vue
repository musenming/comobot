<script setup lang="ts">
import { ref } from 'vue'
import { NInput } from 'naive-ui'

defineProps<{
  value?: string
  placeholder?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:value', val: string): void
}>()

const visible = ref(false)
</script>

<template>
  <div class="secret-input">
    <NInput
      :value="value"
      :type="visible ? 'text' : 'password'"
      :placeholder="placeholder || 'Enter secret...'"
      :disabled="disabled"
      @update:value="(v: string) => emit('update:value', v)"
    />
    <button
      class="toggle-btn"
      type="button"
      :aria-label="visible ? 'Hide secret' : 'Show secret'"
      @click="visible = !visible"
    >
      {{ visible ? '◉' : '◎' }}
    </button>
  </div>
</template>

<style scoped>
.secret-input {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}
.secret-input :deep(.n-input) {
  flex: 1;
}
.toggle-btn {
  position: absolute;
  right: 8px;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
  transition: color 150ms;
  z-index: 1;
}
.toggle-btn:hover {
  color: var(--text-primary);
}
</style>
