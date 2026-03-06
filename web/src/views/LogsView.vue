<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { NInput, NSelect } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useWebSocket } from '../composables/useWebSocket'
import api from '../api/client'

const { connected, messages: wsMessages } = useWebSocket('/ws/logs')

const logs = ref<any[]>([])
const loading = ref(true)
const search = ref('')
const levelFilter = ref<string>('')
const autoScroll = ref(true)
const logContainer = ref<HTMLDivElement>()

const levelOptions = [
  { label: 'All', value: '' },
  { label: 'Info', value: 'info' },
  { label: 'Warn', value: 'warn' },
  { label: 'Error', value: 'error' },
]

const filteredLogs = computed(() => {
  let result = logs.value
  if (levelFilter.value) {
    result = result.filter(l => l.level === levelFilter.value)
  }
  if (search.value) {
    const q = search.value.toLowerCase()
    result = result.filter(l =>
      (l.event || '').toLowerCase().includes(q) ||
      (l.detail || '').toLowerCase().includes(q) ||
      (l.module || '').toLowerCase().includes(q)
    )
  }
  return result
})

const levelColor: Record<string, string> = {
  info: 'var(--accent-blue)',
  warn: 'var(--accent-yellow)',
  error: 'var(--accent-red)',
}

// Load initial logs from REST API
onMounted(async () => {
  try {
    const { data } = await api.get('/logs?limit=200')
    logs.value = (data || []).reverse()
  } catch {
    // empty
  } finally {
    loading.value = false
  }
})

// Watch for WS messages and append
import { watch } from 'vue'
watch(wsMessages, (msgs) => {
  if (msgs.length > logs.value.length) {
    const newOnes = msgs.slice(logs.value.length)
    logs.value.push(...newOnes)
    if (autoScroll.value) {
      nextTick(() => {
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      })
    }
  }
}, { deep: true })

function handleScroll() {
  if (!logContainer.value) return
  const el = logContainer.value
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 50
  autoScroll.value = atBottom
}

const expandedId = ref<number | null>(null)

function toggleExpand(idx: number) {
  expandedId.value = expandedId.value === idx ? null : idx
}
</script>

<template>
  <PageLayout title="Logs" description="Real-time system audit log">
    <template #actions>
      <StatusBadge :status="connected ? 'online' : 'offline'" />
    </template>

    <!-- Filter toolbar -->
    <div class="log-toolbar">
      <NSelect
        :value="levelFilter"
        :options="levelOptions"
        placeholder="Level"
        clearable
        size="small"
        style="width: 120px"
        @update:value="(v: string) => levelFilter = v || ''"
      />
      <NInput
        v-model:value="search"
        placeholder="Search logs..."
        size="small"
        clearable
        style="max-width: 300px"
      />
    </div>

    <!-- Log viewer -->
    <div class="log-viewer" ref="logContainer" @scroll="handleScroll">
      <div v-if="loading" class="log-loading">Loading logs...</div>
      <div v-else-if="filteredLogs.length === 0" class="log-empty">No logs match your filter</div>
      <div
        v-for="(log, idx) in filteredLogs"
        :key="idx"
        class="log-line"
        :class="{ error: log.level === 'error', clickable: log.detail }"
        @click="log.detail ? toggleExpand(idx) : null"
      >
        <span class="log-time">{{ (log.timestamp || '').replace('T', ' ').slice(0, 19) }}</span>
        <span class="log-level" :style="{ color: levelColor[log.level] || 'var(--text-muted)' }">
          {{ (log.level || 'info').toUpperCase().padEnd(5) }}
        </span>
        <span class="log-module">{{ log.module || '-' }}</span>
        <span class="log-event">{{ log.event || '' }}</span>
        <div v-if="expandedId === idx && log.detail" class="log-detail">{{ log.detail }}</div>
      </div>
    </div>

    <div v-if="!autoScroll" class="scroll-badge" @click="autoScroll = true; logContainer?.scrollTo({ top: logContainer.scrollHeight, behavior: 'smooth' })">
      ↓ New logs
    </div>
  </PageLayout>
</template>

<style scoped>
.log-toolbar {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
  align-items: center;
}
.log-viewer {
  background: #060608;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: var(--text-sm);
  line-height: 28px;
  max-height: 65vh;
  overflow-y: auto;
  min-height: 300px;
}
:root:not(.dark) .log-viewer {
  background: #F6F6F8;
}
.log-loading,
.log-empty {
  color: var(--text-muted);
  text-align: center;
  padding: var(--space-8);
}
.log-line {
  display: flex;
  gap: var(--space-3);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  flex-wrap: wrap;
}
.log-line.clickable {
  cursor: pointer;
}
.log-line:hover {
  background: rgba(255, 255, 255, 0.03);
}
.log-line.error {
  background: rgba(239, 68, 68, 0.06);
}
.log-time {
  color: var(--text-muted);
  flex-shrink: 0;
}
.log-level {
  font-weight: 600;
  flex-shrink: 0;
  width: 40px;
}
.log-module {
  color: var(--accent-blue);
  flex-shrink: 0;
  min-width: 80px;
}
.log-event {
  color: var(--text-primary);
  flex: 1;
  word-break: break-word;
}
.log-detail {
  width: 100%;
  padding: var(--space-2) var(--space-4);
  margin: var(--space-1) 0;
  background: var(--bg-muted);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
  font-size: var(--text-xs);
}
.scroll-badge {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--accent-blue);
  color: white;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  box-shadow: var(--shadow-md);
  z-index: 50;
}
</style>
