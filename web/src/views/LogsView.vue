<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { NInput, NSelect, NTabs, NTabPane } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useWebSocket } from '../composables/useWebSocket'
import { useI18n } from '../composables/useI18n'
import api from '../api/client'

const { t } = useI18n()

// --- Tab state ---
const activeTab = ref<'audit' | 'gateway'>('audit')

// --- Audit logs (existing) ---
const { connected, messages: wsMessages } = useWebSocket('/ws/logs')

const auditLogs = ref<any[]>([])
const auditLoading = ref(true)
const search = ref('')
const levelFilter = ref<string>('')
const autoScroll = ref(true)
const logContainer = ref<HTMLDivElement>()

const levelOptions = computed(() => [
  { label: t('logs.all'), value: '' },
  { label: t('logs.info'), value: 'info' },
  { label: t('logs.warn'), value: 'warn' },
  { label: t('common.error'), value: 'error' },
])

const filteredAuditLogs = computed(() => {
  let result = auditLogs.value
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
  debug: 'var(--text-muted)',
}

// Load initial audit logs
onMounted(async () => {
  try {
    const { data } = await api.get('/logs?limit=200')
    auditLogs.value = (data || []).reverse()
  } catch {
    // empty
  } finally {
    auditLoading.value = false
  }
})

// Watch WS messages for audit logs
watch(wsMessages, (msgs) => {
  if (msgs.length > auditLogs.value.length) {
    const newOnes = msgs.slice(auditLogs.value.length)
    auditLogs.value.push(...newOnes)
    if (autoScroll.value && activeTab.value === 'audit') {
      nextTick(() => {
        if (logContainer.value) {
          logContainer.value.scrollTop = logContainer.value.scrollHeight
        }
      })
    }
  }
}, { deep: true })

// --- Gateway logs ---
const gatewayLogs = ref<any[]>([])
const gatewayLoading = ref(false)
const gatewaySearch = ref('')
const gatewayLevelFilter = ref<string>('')
const gatewayContainer = ref<HTMLDivElement>()

const filteredGatewayLogs = computed(() => {
  let result = gatewayLogs.value
  if (gatewayLevelFilter.value) {
    result = result.filter(l => l.level === gatewayLevelFilter.value)
  }
  if (gatewaySearch.value) {
    const q = gatewaySearch.value.toLowerCase()
    result = result.filter(l => (l.raw || l.message || '').toLowerCase().includes(q))
  }
  return result
})

async function loadGatewayLogs() {
  gatewayLoading.value = true
  try {
    const { data } = await api.get('/logs/gateway?limit=1000')
    gatewayLogs.value = data || []
    nextTick(() => {
      if (gatewayContainer.value) {
        gatewayContainer.value.scrollTop = gatewayContainer.value.scrollHeight
      }
    })
  } catch {
    gatewayLogs.value = []
  } finally {
    gatewayLoading.value = false
  }
}

// Load gateway logs when tab switches to gateway
watch(activeTab, (tab) => {
  if (tab === 'gateway' && gatewayLogs.value.length === 0) {
    loadGatewayLogs()
  }
})

// --- Shared ---
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
  <PageLayout :title="t('logs.title')" :description="t('logs.subtitle')">
    <template #actions>
      <StatusBadge :status="connected ? 'online' : 'offline'" />
    </template>

    <NTabs v-model:value="activeTab" type="segment" style="margin-bottom: 16px">
      <NTabPane :name="'audit'" :tab="t('logs.auditTab')">
        <!-- Audit filter toolbar -->
        <div class="log-toolbar">
          <NSelect
            :value="levelFilter"
            :options="levelOptions"
            :placeholder="t('logs.level')"
            clearable
            size="small"
            style="width: 120px"
            @update:value="(v: string) => levelFilter = v || ''"
          />
          <NInput
            v-model:value="search"
            :placeholder="t('logs.searchPlaceholder')"
            size="small"
            clearable
            style="max-width: 300px"
          />
        </div>

        <!-- Audit log viewer -->
        <div class="log-viewer" ref="logContainer" @scroll="handleScroll">
          <div v-if="auditLoading" class="log-loading">{{ t('logs.loadingLogs') }}</div>
          <div v-else-if="filteredAuditLogs.length === 0" class="log-empty">{{ t('logs.noLogsMatch') }}</div>
          <div
            v-for="(log, idx) in filteredAuditLogs"
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

        <div v-if="!autoScroll && activeTab === 'audit'" class="scroll-badge" @click="autoScroll = true; logContainer?.scrollTo({ top: logContainer.scrollHeight, behavior: 'smooth' })">
          ↓ {{ t('logs.newLogs') }}
        </div>
      </NTabPane>

      <NTabPane :name="'gateway'" :tab="t('logs.gatewayTab')">
        <!-- Gateway filter toolbar -->
        <div class="log-toolbar">
          <NSelect
            :value="gatewayLevelFilter"
            :options="levelOptions"
            :placeholder="t('logs.level')"
            clearable
            size="small"
            style="width: 120px"
            @update:value="(v: string) => gatewayLevelFilter = v || ''"
          />
          <NInput
            v-model:value="gatewaySearch"
            :placeholder="t('logs.searchPlaceholder')"
            size="small"
            clearable
            style="max-width: 300px"
          />
          <button class="refresh-btn" @click="loadGatewayLogs" :disabled="gatewayLoading">
            {{ t('logs.refresh') }}
          </button>
        </div>

        <!-- Gateway log viewer -->
        <div class="log-viewer" ref="gatewayContainer">
          <div v-if="gatewayLoading" class="log-loading">{{ t('logs.loadingLogs') }}</div>
          <div v-else-if="filteredGatewayLogs.length === 0" class="log-empty">{{ t('logs.noLogsMatch') }}</div>
          <div
            v-for="(log, idx) in filteredGatewayLogs"
            :key="idx"
            class="log-line"
            :class="{ error: log.level === 'error', warn: log.level === 'warn' }"
          >
            <template v-if="log.timestamp">
              <span class="log-time">{{ log.timestamp.slice(0, 19) }}</span>
              <span class="log-level" :style="{ color: levelColor[log.level] || 'var(--text-muted)' }">
                {{ (log.level || 'info').toUpperCase().padEnd(5) }}
              </span>
              <span class="log-module">{{ log.module || '-' }}</span>
              <span class="log-event">{{ log.message || '' }}</span>
            </template>
            <template v-else>
              <span class="log-event plain-line">{{ log.message }}</span>
            </template>
          </div>
        </div>
      </NTabPane>
    </NTabs>
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
.log-line.warn {
  background: rgba(234, 179, 8, 0.04);
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
.plain-line {
  color: var(--text-secondary);
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
.refresh-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-muted);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.refresh-btn:hover {
  background: var(--bg-hover, var(--border));
}
.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
