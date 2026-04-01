<script setup lang="ts">
import ProcessToolCall from './ProcessToolCall.vue'
import ProcessToolGroup from './ProcessToolGroup.vue'
import ProcessPlanCard from './ProcessPlanCard.vue'
import ProcessMemoryRecall from './ProcessMemoryRecall.vue'
import ProcessReflection from './ProcessReflection.vue'
import ProcessEscalation from './ProcessEscalation.vue'
import AgentBadge from './AgentBadge.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  processType: string
  data: any
  timestamp?: string
}>()

// Color accents for left border by process type
const borderColors: Record<string, string> = {
  tool_call: 'var(--text-muted)',
  tool_hint: 'var(--accent-yellow)',
  memory_recall: '#eab308',
  plan_created: 'var(--accent-blue)',
  plan_step: 'var(--accent-blue)',
  plan_progress: 'var(--accent-blue)',
  plan_complete: 'var(--accent-green)',
  agent_spawn: 'rgba(168, 85, 247, 0.6)',
  agent_result: 'rgba(168, 85, 247, 0.6)',
  reflection: 'var(--accent-green)',
  escalation: 'var(--accent-yellow)',
  thinking: 'var(--text-muted)',
}

function formatTime(ts: string | undefined): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}
</script>

<template>
  <div
    class="process-msg"
    :class="{ 'process-msg--plan': processType.startsWith('plan_') }"
    :style="{ '--pm-accent': borderColors[processType] || 'var(--text-muted)' }"
  >
    <!-- Tool call (single) -->
    <ProcessToolCall v-if="processType === 'tool_call'" :data="data" />

    <!-- Tool group (multiple) -->
    <ProcessToolGroup v-else-if="processType === 'tool_group'" :items="data.items || []" />

    <!-- Plan created -->
    <ProcessPlanCard v-else-if="processType === 'plan_created'" :data="data" />

    <!-- Plan step update (inline) -->
    <div v-else-if="processType === 'plan_step'" class="pm-inline">
      <span class="pm-inline-icon" :class="[`pm-status--${data.status || 'pending'}`]">
        {{ data.status === 'done' ? '\u2713' : data.status === 'failed' ? '\u2717' : '\u25CB' }}
      </span>
      <span class="pm-inline-label">{{ t('process.plan_step').replace('{id}', data.step_id || '') }}</span>
      <AgentBadge v-if="data.agent_type" :type="data.agent_type" />
      <span v-if="data.progress" class="pm-inline-text">{{ data.progress }}</span>
    </div>

    <!-- Memory recall -->
    <ProcessMemoryRecall v-else-if="processType === 'memory_recall'" :data="data" />

    <!-- Agent spawn -->
    <div v-else-if="processType === 'agent_spawn'" class="pm-inline">
      <span class="pm-inline-icon">&#9654;</span>
      <AgentBadge :type="data.agent_type || 'general'" />
      <span class="pm-inline-text">{{ data.task || '' }}</span>
    </div>

    <!-- Agent result -->
    <div v-else-if="processType === 'agent_result'" class="pm-inline">
      <span class="pm-inline-icon pm-status--done">&#10003;</span>
      <AgentBadge :type="data.agent_type || 'general'" />
      <span class="pm-inline-text">{{ data.summary || '' }}</span>
    </div>

    <!-- Reflection -->
    <ProcessReflection v-else-if="processType === 'reflection'" :data="data" />

    <!-- Escalation -->
    <ProcessEscalation v-else-if="processType === 'escalation'" :data="data" />

    <!-- Plan progress -->
    <div v-else-if="processType === 'plan_progress'" class="pm-inline">
      <span class="pm-inline-icon pm-status--running">&#9654;</span>
      <span class="pm-inline-label">{{ t('process.plan_created') }}</span>
      <span class="pm-inline-text">{{ data.completed }}/{{ data.total }}</span>
    </div>

    <!-- Plan complete -->
    <div v-else-if="processType === 'plan_complete'" class="pm-plan-complete">
      <div class="pm-inline">
        <span class="pm-inline-icon pm-status--done">&#10003;</span>
        <span class="pm-inline-label">{{ data.goal }}</span>
      </div>
      <div v-if="data.summary" class="pm-complete-summary">{{ data.summary }}</div>
    </div>

    <!-- Thinking (animated dots, hide when status=end) -->
    <div v-else-if="processType === 'thinking' && data.status !== 'end'" class="pm-thinking">
      <span class="pm-dot" /><span class="pm-dot" /><span class="pm-dot" />
    </div>

    <!-- Tool hint: inline display of tool being called -->
    <div v-else-if="processType === 'tool_hint'" class="pm-inline">
      <span class="pm-inline-icon pm-status--running">&#9654;</span>
      <span class="pm-inline-label">{{ typeof data.content === 'string' ? data.content : JSON.stringify(data.content) }}</span>
      <span v-if="data.step_id" class="pm-inline-text">{{ data.step_id }}</span>
    </div>

    <!-- Fallback: unknown process type -->
    <div v-else class="pm-inline">
      <span class="pm-inline-label">{{ processType }}</span>
      <span class="pm-inline-text">{{ typeof data === 'string' ? data : JSON.stringify(data) }}</span>
    </div>

    <!-- Timestamp -->
    <span v-if="timestamp" class="pm-time">{{ formatTime(timestamp) }}</span>
  </div>
</template>

<style scoped>
.process-msg {
  position: relative;
  margin: 2px 0;
  padding-left: 3px;
  border-left: 2px solid var(--pm-accent);
  background: var(--bg-muted);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  max-width: 85%;
  transition: background 120ms;
}
.process-msg--plan {
  max-width: 50%;
}
.process-msg:hover {
  background: rgba(59, 130, 246, 0.05);
}
.pm-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}
.pm-inline-icon {
  font-size: 11px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
  color: var(--text-muted);
}
.pm-status--done { color: var(--accent-green) !important; }
.pm-status--failed { color: var(--accent-red) !important; }
.pm-status--running { color: var(--accent-blue) !important; }
.pm-status--pending { color: var(--text-muted) !important; }
.pm-plan-complete {
  padding: 5px 10px;
}
.pm-complete-summary {
  padding: 4px 0 2px 20px;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.5;
  white-space: pre-line;
}
.pm-inline-label {
  font-weight: 500;
  font-size: var(--text-xs);
  white-space: nowrap;
}
.pm-inline-text {
  color: var(--text-primary);
  font-size: var(--text-xs);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pm-time {
  position: absolute;
  top: 4px;
  right: 8px;
  font-size: 9px;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 120ms;
}
.process-msg:hover .pm-time { opacity: 0.7; }

/* Thinking dots */
.pm-thinking {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 8px 12px;
}
.pm-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: pm-bounce 1.2s ease-in-out infinite;
}
.pm-dot:nth-child(2) { animation-delay: 0.15s; }
.pm-dot:nth-child(3) { animation-delay: 0.3s; }
@keyframes pm-bounce {
  0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}
</style>
