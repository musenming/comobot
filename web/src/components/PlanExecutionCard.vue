<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from '../composables/useI18n'
import AgentBadge from './AgentBadge.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const { t } = useI18n()

export interface PlanToolStep {
  name: string
  content: string
  done: boolean
  startTime?: number
}

export interface PlanStep {
  id: string
  description: string
  agent_type?: string
  status?: 'pending' | 'running' | 'done' | 'failed'
  toolSteps?: PlanToolStep[]
  progress?: string
  result_summary?: string
}

const props = defineProps<{
  goal: string
  steps: PlanStep[]
  status?: 'executing' | 'done' | 'failed'
  summary?: string
  planId?: string
}>()

const expandedSteps = ref<Set<string>>(new Set())

// Auto-expand running steps
watch(
  () => props.steps.map(s => s.status),
  () => {
    for (const step of props.steps) {
      if (step.status === 'running') {
        expandedSteps.value.add(step.id)
      }
    }
  },
  { immediate: true, deep: true },
)

function toggleStep(id: string) {
  if (expandedSteps.value.has(id)) {
    expandedSteps.value.delete(id)
  } else {
    expandedSteps.value.add(id)
  }
}

const doneCount = computed(() => props.steps.filter(s => s.status === 'done').length)
const totalCount = computed(() => props.steps.length)
const progressPct = computed(() => (totalCount.value ? (doneCount.value / totalCount.value) * 100 : 0))
const isComplete = computed(() => props.status === 'done' || (doneCount.value === totalCount.value && totalCount.value > 0))
const isFailed = computed(() => props.status === 'failed')

// SVG progress ring
const ringRadius = 18
const ringCircumference = 2 * Math.PI * ringRadius
const ringOffset = computed(() => ringCircumference - (progressPct.value / 100) * ringCircumference)

function statusIcon(status: string | undefined): string {
  switch (status) {
    case 'done': return '✓'
    case 'failed': return '✕'
    case 'running': return '▸'
    default: return '·'
  }
}

</script>

<template>
  <div
    class="pec"
    :class="{
      'pec--done': isComplete,
      'pec--failed': isFailed,
      'pec--exec': !isComplete && !isFailed,
    }"
  >
    <!-- Scanning line effect for executing state -->
    <div v-if="!isComplete && !isFailed" class="pec-scan" />

    <!-- Accent edge -->
    <div class="pec-edge" />

    <!-- Header -->
    <div class="pec-head">
      <div class="pec-head-left">
        <div class="pec-icon-wrap">
          <svg class="pec-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M3 3h10M3 6.5h7M3 10h8.5M3 13.5h5" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" />
          </svg>
        </div>
        <div class="pec-head-text">
          <span class="pec-label">{{ t('process.plan_created') }}</span>
          <span class="pec-goal">{{ goal }}</span>
        </div>
      </div>

      <!-- Progress ring -->
      <div class="pec-ring-box" :title="`${doneCount}/${totalCount}`">
        <svg class="pec-ring" width="44" height="44" viewBox="0 0 44 44">
          <!-- Background track -->
          <circle
            cx="22" cy="22" :r="ringRadius"
            fill="none"
            stroke="var(--pec-ring-bg, rgba(255,255,255,0.06))"
            stroke-width="3"
          />
          <!-- Progress arc -->
          <circle
            cx="22" cy="22" :r="ringRadius"
            fill="none"
            class="pec-ring-arc"
            :class="{ 'pec-ring-arc--done': isComplete, 'pec-ring-arc--fail': isFailed }"
            stroke-width="3"
            stroke-linecap="round"
            :stroke-dasharray="ringCircumference"
            :stroke-dashoffset="ringOffset"
          />
          <!-- Glow overlay for running -->
          <circle
            v-if="!isComplete && !isFailed && progressPct > 0"
            cx="22" cy="22" :r="ringRadius"
            fill="none"
            class="pec-ring-glow"
            stroke-width="6"
            stroke-linecap="round"
            :stroke-dasharray="ringCircumference"
            :stroke-dashoffset="ringOffset"
          />
        </svg>
        <span class="pec-ring-num">{{ doneCount }}<span class="pec-ring-sep">/</span>{{ totalCount }}</span>
      </div>
    </div>

    <!-- Steps Timeline -->
    <div class="pec-steps">
      <div
        v-for="(step, idx) in steps"
        :key="step.id"
        class="pec-step"
        :class="[`pec-step--${step.status || 'pending'}`]"
      >
        <!-- Timeline connector -->
        <div class="pec-tl">
          <div v-if="idx > 0" class="pec-tl-wire pec-tl-wire--top" />
          <div class="pec-tl-node" :class="[`pec-node--${step.status || 'pending'}`]">
            <span class="pec-node-icon">{{ statusIcon(step.status) }}</span>
            <!-- Pulse rings for running -->
            <span v-if="step.status === 'running'" class="pec-node-pulse" />
            <span v-if="step.status === 'running'" class="pec-node-pulse pec-node-pulse--delayed" />
          </div>
          <div v-if="idx < steps.length - 1" class="pec-tl-wire pec-tl-wire--bot" />
        </div>

        <!-- Step content -->
        <div class="pec-step-body">
          <button class="pec-step-btn" @click="toggleStep(step.id)">
            <span class="pec-step-desc">{{ step.description }}</span>
            <AgentBadge
              v-if="step.agent_type && step.agent_type !== 'general'"
              :type="step.agent_type"
            />
            <span
              v-if="(step.toolSteps && step.toolSteps.length > 0) || step.status === 'running'"
              class="pec-chev"
              :class="{ 'pec-chev--open': expandedSteps.has(step.id) }"
            >‹</span>
          </button>

          <!-- Live progress text -->
          <div v-if="step.status === 'running' && step.progress" class="pec-step-prog">
            <span class="pec-prog-pulse" />
            {{ step.progress }}
          </div>

          <!-- Expanded tool steps panel -->
          <div
            v-if="step.toolSteps && step.toolSteps.length > 0"
            class="pec-tools-panel"
            :class="{ 'pec-tools-panel--open': expandedSteps.has(step.id) }"
          >
            <div class="pec-tools-inner">
              <div
                v-for="(ts, ti) in step.toolSteps"
                :key="ti"
                class="pec-tool"
                :class="{
                  'pec-tool--done': ts.done,
                  'pec-tool--active': !ts.done && ti === step.toolSteps!.length - 1,
                }"
              >
                <span class="pec-tool-indicator" />
                <span class="pec-tool-name">{{ ts.name }}</span>
                <span v-if="ts.content" class="pec-tool-content">{{ ts.content }}</span>
                <span v-if="ts.done" class="pec-tool-ok">✓</span>
                <span v-else-if="ti === step.toolSteps!.length - 1" class="pec-tool-spin" />
              </div>
            </div>
          </div>

          <!-- Result summary -->
          <div v-if="step.result_summary" class="pec-step-result">
            {{ step.result_summary }}
          </div>
        </div>
      </div>
    </div>

    <!-- Completion banner -->
    <div v-if="isComplete && summary" class="pec-done-bar">
      <div class="pec-done-icon">✓</div>
      <MarkdownRenderer :content="summary" class="pec-done-text" />
    </div>
  </div>
</template>

<style scoped>
/* ─── Card Shell ──────────────────────────────────────── */
.pec {
  --pec-accent: var(--accent-blue);
  --pec-glow: rgba(59, 130, 246, 0.15);
  --pec-ring-bg: rgba(255, 255, 255, 0.04);

  position: relative;
  border-radius: var(--radius-md);
  background:
    linear-gradient(
      168deg,
      rgba(59, 130, 246, 0.04) 0%,
      transparent 40%,
      rgba(59, 130, 246, 0.02) 100%
    ),
    var(--surface);
  border: 1px solid rgba(59, 130, 246, 0.08);
  overflow: hidden;
  transition: border-color 0.5s, box-shadow 0.5s;
}
.pec--exec {
  box-shadow:
    0 0 0 1px var(--pec-glow),
    0 8px 32px -8px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
.pec--done {
  --pec-accent: var(--accent-green);
  --pec-glow: rgba(34, 197, 94, 0.12);
  box-shadow:
    0 0 0 1px var(--pec-glow),
    0 4px 20px -4px rgba(0, 0, 0, 0.25);
}
.pec--failed {
  --pec-accent: var(--accent-red);
  --pec-glow: rgba(239, 68, 68, 0.12);
}

/* ─── Scanning Line ───────────────────────────────────── */
.pec-scan {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    var(--pec-accent) 30%,
    rgba(59, 130, 246, 0.6) 50%,
    var(--pec-accent) 70%,
    transparent 100%
  );
  opacity: 0.5;
  animation: pec-scan-move 3.5s ease-in-out infinite;
  z-index: 2;
}
@keyframes pec-scan-move {
  0% { top: 0; opacity: 0; }
  10% { opacity: 0.6; }
  90% { opacity: 0.6; }
  100% { top: 100%; opacity: 0; }
}

/* ─── Edge Accent ─────────────────────────────────────── */
.pec-edge {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 2px;
  background: var(--pec-accent);
  opacity: 0.5;
  transition: opacity 0.6s, background 0.6s;
}
.pec--exec .pec-edge {
  opacity: 0.8;
  box-shadow: 0 0 8px var(--pec-glow), 0 0 20px var(--pec-glow);
  animation: pec-edge-breathe 2.8s ease-in-out infinite;
}
.pec--done .pec-edge {
  opacity: 0.6;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.2);
}
@keyframes pec-edge-breathe {
  0%, 100% { opacity: 0.8; }
  50% { opacity: 0.4; }
}

/* ─── Header ──────────────────────────────────────────── */
.pec-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-3) var(--space-2) calc(var(--space-3) + 8px);
}
.pec-head-left {
  display: flex;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
}
.pec-icon-wrap {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--pec-accent);
  opacity: 0.7;
}
.pec-head-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pec-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--pec-accent);
  opacity: 0.7;
}
.pec-goal {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.45;
}

/* ─── Progress Ring ───────────────────────────────────── */
.pec-ring-box {
  flex-shrink: 0;
  position: relative;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pec-ring {
  transform: rotate(-90deg);
}
.pec-ring-arc {
  stroke: var(--pec-accent);
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1), stroke 0.5s;
  filter: drop-shadow(0 0 3px var(--pec-glow));
}
.pec-ring-arc--done {
  stroke: var(--accent-green);
  filter: drop-shadow(0 0 4px rgba(34, 197, 94, 0.3));
}
.pec-ring-arc--fail {
  stroke: var(--accent-red);
}
.pec-ring-glow {
  stroke: var(--pec-accent);
  opacity: 0.15;
  transition: stroke-dashoffset 0.8s cubic-bezier(0.4, 0, 0.2, 1);
  filter: blur(3px);
}
.pec-ring-num {
  position: absolute;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  letter-spacing: -0.02em;
}
.pec-ring-sep {
  opacity: 0.35;
  margin: 0 0.5px;
}

/* ─── Steps Container ─────────────────────────────────── */
.pec-steps {
  padding: 0 var(--space-3) var(--space-2) calc(var(--space-3) + 8px);
  display: flex;
  flex-direction: column;
}

/* ─── Single Step ─────────────────────────────────────── */
.pec-step {
  display: flex;
  gap: var(--space-2);
  min-height: 36px;
}

/* ─── Timeline ────────────────────────────────────────── */
.pec-tl {
  flex-shrink: 0;
  width: 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}
.pec-tl-wire {
  width: 1px;
  flex: 1;
  background: var(--border);
  transition: background 0.4s;
}
.pec-step--done .pec-tl-wire {
  background: rgba(34, 197, 94, 0.2);
}
.pec-step--running .pec-tl-wire--top {
  background: linear-gradient(to bottom, rgba(34, 197, 94, 0.2), rgba(59, 130, 246, 0.4));
}
.pec-tl-node {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
  transition: background 0.3s, border-color 0.3s, box-shadow 0.3s;
  background: var(--bg-muted);
  border: 1.5px solid var(--border);
}
.pec-node--done {
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.35);
}
.pec-node--running {
  background: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.5);
  box-shadow: 0 0 10px rgba(59, 130, 246, 0.2);
}
.pec-node--failed {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.35);
}
.pec-node-icon {
  font-size: 10px;
  line-height: 1;
  font-weight: 700;
}
.pec-node--pending .pec-node-icon { color: var(--text-muted); }
.pec-node--done .pec-node-icon { color: var(--accent-green); }
.pec-node--running .pec-node-icon { color: var(--accent-blue); }
.pec-node--failed .pec-node-icon { color: var(--accent-red); }

/* Pulse rings for running node */
.pec-node-pulse {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid rgba(59, 130, 246, 0.3);
  animation: pec-pulse-ring 2.4s ease-out infinite;
}
.pec-node-pulse--delayed {
  animation-delay: 1.2s;
}
@keyframes pec-pulse-ring {
  0% { transform: scale(0.8); opacity: 0.8; }
  100% { transform: scale(1.8); opacity: 0; }
}

/* ─── Step Body ───────────────────────────────────────── */
.pec-step-body {
  flex: 1;
  min-width: 0;
  padding-bottom: var(--space-1);
}
.pec-step-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: 5px 8px;
  margin: 0 -8px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: var(--radius-sm);
  font-family: inherit;
  text-align: left;
  transition: background 0.15s;
}
.pec-step-btn:hover {
  background: rgba(255, 255, 255, 0.025);
}
.pec-step-desc {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.45;
  min-width: 0;
}
.pec-step--done .pec-step-desc {
  color: var(--text-muted);
}
.pec-step--running .pec-step-desc {
  color: var(--text-primary);
  font-weight: 500;
}

/* ─── Chevron ─────────────────────────────────────────── */
.pec-chev {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--text-muted);
  transform: rotate(-90deg);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  line-height: 1;
  opacity: 0.6;
}
.pec-chev--open {
  transform: rotate(0deg);
  opacity: 1;
}

/* ─── Step Progress ───────────────────────────────────── */
.pec-step-prog {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--accent-blue);
  padding: 2px 8px;
  opacity: 0.85;
}
.pec-prog-pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-blue);
  flex-shrink: 0;
  animation: pec-prog-blink 1.5s ease-in-out infinite;
}
@keyframes pec-prog-blink {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px rgba(59, 130, 246, 0.4); }
  50% { opacity: 0.3; box-shadow: none; }
}

/* ─── Tool Steps Panel ────────────────────────────────── */
.pec-tools-panel {
  overflow: hidden;
  max-height: 0;
  opacity: 0;
  transition: max-height 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s;
}
.pec-tools-panel--open {
  max-height: 800px;
  opacity: 1;
}
.pec-tools-inner {
  padding: var(--space-1) 0 var(--space-1) 4px;
  border-left: 1px solid rgba(59, 130, 246, 0.1);
  margin-left: 2px;
}
.pec-tool {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0 3px 10px;
  font-size: 10px;
  color: var(--text-muted);
  transition: color 0.2s;
  position: relative;
  min-height: 22px;
}
.pec-tool--done {
  color: var(--text-secondary);
}
.pec-tool--active {
  color: var(--text-primary);
}

/* Tool indicator dot */
.pec-tool-indicator {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
  transition: background 0.3s, box-shadow 0.3s;
}
.pec-tool--done .pec-tool-indicator {
  background: var(--accent-green);
  box-shadow: 0 0 4px rgba(34, 197, 94, 0.3);
}
.pec-tool--active .pec-tool-indicator {
  background: var(--accent-blue);
  box-shadow: 0 0 6px rgba(59, 130, 246, 0.4);
  animation: pec-tool-blink 1s ease-in-out infinite;
}
@keyframes pec-tool-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.pec-tool-name {
  flex-shrink: 0;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  letter-spacing: -0.01em;
  white-space: nowrap;
}
.pec-tool-content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.6;
  font-size: 9px;
}
.pec-tool-ok {
  font-size: 9px;
  color: var(--accent-green);
  font-weight: 700;
  flex-shrink: 0;
}

/* Spinning indicator for active tool */
.pec-tool-spin {
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(59, 130, 246, 0.2);
  border-top-color: var(--accent-blue);
  border-radius: 50%;
  animation: pec-spin 0.7s linear infinite;
  flex-shrink: 0;
}
@keyframes pec-spin {
  to { transform: rotate(360deg); }
}

/* ─── Step Result ─────────────────────────────────────── */
.pec-step-result {
  font-size: 10px;
  color: var(--text-muted);
  padding: 2px 8px;
  line-height: 1.4;
  opacity: 0.8;
}

/* ─── Completion Banner ───────────────────────────────── */
.pec-done-bar {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  padding: var(--space-2) var(--space-3) var(--space-3) calc(var(--space-3) + 8px);
  border-top: 1px solid rgba(34, 197, 94, 0.08);
  background: linear-gradient(180deg, rgba(34, 197, 94, 0.025) 0%, transparent 100%);
}
.pec-done-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: rgba(34, 197, 94, 0.1);
  color: var(--accent-green);
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.15);
}
.pec-done-text {
  flex: 1;
  min-width: 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  line-height: 1.5;
}
.pec-done-text :deep(.markdown-body) {
  font-size: var(--text-xs);
  line-height: 1.5;
  color: var(--text-secondary);
}
.pec-done-text :deep(.markdown-body p) {
  margin: 0 0 var(--space-1);
}
.pec-done-text :deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}
</style>
