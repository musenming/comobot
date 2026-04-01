<script setup lang="ts">
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  type: string
}>()

const palette: Record<string, { bg: string; fg: string; glow: string }> = {
  researcher: { bg: 'rgba(59, 130, 246, 0.08)', fg: 'var(--accent-blue)', glow: 'rgba(59, 130, 246, 0.15)' },
  coder:      { bg: 'rgba(34, 197, 94, 0.08)',  fg: 'var(--accent-green)', glow: 'rgba(34, 197, 94, 0.15)' },
  analyst:    { bg: 'rgba(168, 85, 247, 0.08)', fg: '#9333ea', glow: 'rgba(168, 85, 247, 0.15)' },
  general:    { bg: 'rgba(107, 114, 128, 0.06)', fg: 'var(--text-secondary)', glow: 'rgba(107, 114, 128, 0.1)' },
}

function color(key: 'bg' | 'fg' | 'glow') {
  return (palette[props.type] ?? palette.general)![key]
}
</script>

<template>
  <span
    class="agent-badge"
    :style="{
      '--badge-bg': color('bg'),
      '--badge-fg': color('fg'),
      '--badge-glow': color('glow'),
    }"
  >
    <span class="badge-dot" />
    {{ t(`process.agent.${type}`) || type }}
  </span>
</template>

<style scoped>
.agent-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 10px 2px 8px;
  border-radius: 999px;
  background: var(--badge-bg);
  color: var(--badge-fg);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  white-space: nowrap;
  line-height: 1.8;
  backdrop-filter: blur(4px);
}
.badge-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--badge-fg);
  box-shadow: 0 0 6px var(--badge-glow);
  flex-shrink: 0;
}
</style>
