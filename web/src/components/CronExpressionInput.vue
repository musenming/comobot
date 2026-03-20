<script setup lang="ts">
import { computed } from 'vue'
import { NInput } from 'naive-ui'
import cronstrue from 'cronstrue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  value: string
}>()

const emit = defineEmits<{
  (e: 'update:value', val: string): void
}>()

const humanReadable = computed(() => {
  if (!props.value) return ''
  try {
    return cronstrue.toString(props.value)
  } catch {
    return t('cron.invalidExpression')
  }
})
</script>

<template>
  <div class="cron-input">
    <NInput
      :value="value"
      placeholder="0 8 * * *"
      @update:value="(v: string) => emit('update:value', v)"
    />
    <div v-if="value" class="cron-human" :class="{ invalid: humanReadable === t('cron.invalidExpression') }">
      {{ humanReadable }}
    </div>
  </div>
</template>

<style scoped>
.cron-input {
  width: 100%;
}
.cron-human {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}
.cron-human.invalid {
  color: var(--accent-red);
}
</style>
