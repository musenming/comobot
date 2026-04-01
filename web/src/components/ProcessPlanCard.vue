<script setup lang="ts">
import AgentBadge from './AgentBadge.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  data: {
    goal: string
    steps: Array<{
      id: string
      description: string
      agent_type?: string
      status?: string
      dependencies?: string[]
      progress?: string
      result_summary?: string
    }>
    plan_id?: string
  }
}>()

function stepIcon(status: string | undefined): string {
  switch (status) {
    case 'done': return '\u2713'
    case 'failed': return '\u2717'
    case 'running': return '\u25CB'
    default: return '\u25CB'
  }
}

function stepCount(): { done: number; total: number } {
  const total = props.data.steps.length
  const done = props.data.steps.filter(s => s.status === 'done').length
  return { done, total }
}
</script>

<template>
  <div class="ppc">
    <div class="ppc-header">
      <span class="ppc-icon" aria-hidden="true">&#9776;</span>
      <span class="ppc-title">{{ t('process.plan_created') }}</span>
      <span class="ppc-spacer" />
      <span class="ppc-progress">{{ stepCount().done }}/{{ stepCount().total }}</span>
    </div>
    <div class="ppc-goal">{{ data.goal }}</div>
    <div class="ppc-steps">
      <div
        v-for="step in data.steps"
        :key="step.id"
        class="ppc-step"
        :class="[`ppc-step--${step.status || 'pending'}`]"
      >
        <span class="ppc-step-icon" :class="[`ppc-step-icon--${step.status || 'pending'}`]">
          {{ stepIcon(step.status) }}
        </span>
        <span class="ppc-step-id">{{ step.id }}</span>
        <span class="ppc-step-desc">{{ step.description }}</span>
        <AgentBadge v-if="step.agent_type && step.agent_type !== 'general'" :type="step.agent_type" />
        <span v-if="step.progress" class="ppc-step-progress">{{ step.progress }}</span>
        <span v-if="step.result_summary" class="ppc-step-result">{{ step.result_summary }}</span>
      </div>
    </div>
    <div v-if="stepCount().done === stepCount().total && stepCount().total > 0" class="ppc-complete">
      &#10003; {{ t('process.status.done') }}
    </div>
  </div>
</template>

<style scoped>
.ppc {
  padding: 10px 12px;
}
.ppc-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.ppc-icon {
  font-size: 13px;
  color: var(--text-muted);
}
.ppc-title {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}
.ppc-spacer { flex: 1; }
.ppc-progress {
  font-family: 'SF Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 1px 8px;
  border-radius: 999px;
}
.ppc-goal {
  font-size: var(--text-sm);
  color: var(--text-primary);
  margin-bottom: 8px;
  line-height: 1.5;
}
.ppc-steps {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ppc-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  transition: background 120ms;
}
.ppc-step:hover {
  background: rgba(0, 0, 0, 0.02);
}
.ppc-step-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  flex-shrink: 0;
}
.ppc-step-icon--done { color: var(--accent-green); }
.ppc-step-icon--failed { color: var(--accent-red); }
.ppc-step-icon--running { color: var(--accent-blue); animation: ppc-pulse 1.5s ease-in-out infinite; }
.ppc-step-icon--pending { color: var(--text-muted); }
@keyframes ppc-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.ppc-step-id {
  font-family: 'SF Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
  min-width: 40px;
}
.ppc-step-desc {
  flex: 1;
  color: var(--text-primary);
}
.ppc-step--done .ppc-step-desc { color: var(--text-secondary); }
.ppc-step--running .ppc-step-desc { color: var(--accent-blue); font-weight: 500; }
.ppc-step-progress,
.ppc-step-result {
  font-size: 10px;
  color: var(--text-muted);
}
.ppc-complete {
  margin-top: 6px;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 600;
  color: var(--accent-green);
  letter-spacing: 0.03em;
}
</style>
