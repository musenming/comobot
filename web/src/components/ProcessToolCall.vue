<script setup lang="ts">
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  data: {
    tool: string
    args?: Record<string, any>
    status: string
    result_summary?: string
    duration_ms?: number
  }
}>()

function truncArgs(args: Record<string, any> | undefined, max = 48): string {
  if (!args) return ''
  const s = Object.entries(args).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ')
  return s.length > max ? s.slice(0, max - 1) + '\u2026' : s
}
</script>

<template>
  <div class="ptc" :class="[`ptc--${data.status}`]">
    <span class="ptc-icon" aria-hidden="true">
      <svg v-if="data.status === 'running'" class="ptc-spinner" width="14" height="14" viewBox="0 0 14 14">
        <circle cx="7" cy="7" r="5.5" stroke="var(--accent-blue)" stroke-width="1.5" fill="none" stroke-dasharray="20 14" />
      </svg>
      <template v-else>&#9881;</template>
    </span>
    <code class="ptc-name">{{ data.tool }}</code>
    <span v-if="data.args && Object.keys(data.args).length" class="ptc-args">({{ truncArgs(data.args) }})</span>
    <span class="ptc-spacer" />
    <span class="ptc-badge" :class="`ptc-badge--${data.status}`">
      {{ t(`process.status.${data.status}`) }}
    </span>
    <span v-if="data.duration_ms != null" class="ptc-dur">{{ data.duration_ms < 1000 ? `${data.duration_ms}ms` : `${(data.duration_ms / 1000).toFixed(1)}s` }}</span>
    <span v-if="data.result_summary" class="ptc-summary">&middot; {{ data.result_summary }}</span>
  </div>
</template>

<style scoped>
.ptc {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  min-height: 28px;
  flex-wrap: wrap;
}
.ptc-icon {
  flex-shrink: 0;
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--text-muted);
}
.ptc-spinner {
  animation: ptc-spin 0.9s linear infinite;
}
@keyframes ptc-spin {
  to { transform: rotate(360deg); }
}
.ptc-name {
  font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.ptc-args {
  font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ptc-spacer { flex: 1; }
.ptc-badge {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  padding: 1px 7px;
  border-radius: 999px;
  text-transform: uppercase;
}
.ptc-badge--running { background: rgba(59, 130, 246, 0.1); color: var(--accent-blue); }
.ptc-badge--done { background: rgba(34, 197, 94, 0.1); color: var(--accent-green); }
.ptc-badge--failed { background: rgba(220, 38, 38, 0.1); color: var(--accent-red); }
.ptc-badge--pending { background: rgba(107, 114, 128, 0.08); color: var(--text-muted); }

.ptc-dur {
  font-family: 'SF Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.7;
}
.ptc-summary {
  font-size: 10px;
  color: var(--text-muted);
}
.ptc--running .ptc-name { color: var(--accent-blue); }
</style>
