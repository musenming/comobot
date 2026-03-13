<script setup lang="ts">
import { ref } from 'vue'
import { NButton } from 'naive-ui'

const emit = defineEmits<{ extract: [ids: number[]] }>()

const selecting = ref(false)
const selected = ref(new Set<number>())

function toggleSelect(id: number) {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
}
function cancel() {
  selecting.value = false
  selected.value.clear()
}
function doExtract() {
  emit('extract', [...selected.value])
  cancel()
}

defineExpose({ selecting, selected, toggleSelect })
</script>

<template>
  <div class="message-selector">
    <n-button v-if="!selecting" size="small" quaternary @click="selecting = true">
      Extract Know-how
    </n-button>

    <slot :selecting="selecting" :selected="selected" :toggle-select="toggleSelect" />

    <Transition name="slide-up">
      <div v-if="selecting && selected.size > 0" class="action-bar">
        <span class="selected-count">{{ selected.size }} messages selected</span>
        <n-button type="primary" size="small" @click="doExtract">
          Save as Know-how
        </n-button>
        <n-button size="small" @click="cancel">Cancel</n-button>
      </div>
    </Transition>

    <div v-if="selecting && selected.size === 0" class="hint">
      Click messages to select them, then save as Know-how
      <n-button size="tiny" quaternary @click="cancel">Cancel</n-button>
    </div>
  </div>
</template>

<style scoped>
.action-bar {
  position: sticky;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface);
  border-top: 1px solid var(--border);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}
.selected-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  flex: 1;
}
.hint {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.2s, opacity 0.2s;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
