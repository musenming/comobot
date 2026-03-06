<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NCard } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import StatCard from '../components/StatCard.vue'
import SparklineChart from '../components/SparklineChart.vue'
import StatusBadge from '../components/StatusBadge.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import { useWebSocket } from '../composables/useWebSocket'
import api from '../api/client'

const router = useRouter()
const loading = ref(true)

const stats = ref({
  total_sessions: 0,
  total_messages: 0,
  total_workflows: 0,
  active_workflows: 0,
  cron_jobs: 0,
  recent_errors: 0,
  message_trend: [] as number[],
  running_workflows: [] as any[],
  cron_warnings: [] as any[],
})

async function fetchDashboard() {
  try {
    const { data } = await api.get('/dashboard')
    stats.value = data
  } catch {
    // Dashboard may fail if no data yet
  } finally {
    loading.value = false
  }
}

onMounted(fetchDashboard)

// Live refresh: when WS status updates arrive, re-fetch dashboard stats
const { data: wsStatus } = useWebSocket('/ws/status')
watch(wsStatus, (s) => {
  if (s?.type === 'status') {
    fetchDashboard()
  }
})

function cronStatus(s: string): 'online' | 'offline' | 'error' | 'paused' {
  if (s === 'failed') return 'error'
  if (s === 'disabled') return 'offline'
  return 'online'
}
</script>

<template>
  <PageLayout title="Dashboard" description="System overview">
    <!-- Stats Grid -->
    <div v-if="loading" class="stats-grid">
      <SkeletonCard v-for="i in 6" :key="i" height="120px" />
    </div>
    <div v-else class="stats-grid">
      <StatCard icon="💬" label="Sessions" :value="stats.total_sessions" />
      <StatCard icon="✉" label="Messages" :value="stats.total_messages" />
      <StatCard icon="⚡" label="Active Workflows" :value="stats.active_workflows" />
      <StatCard icon="◈" label="Total Workflows" :value="stats.total_workflows" />
      <StatCard icon="◷" label="Cron Jobs" :value="stats.cron_jobs" />
      <StatCard icon="⚠" label="Errors (24h)" :value="stats.recent_errors" />
    </div>

    <!-- Trend Chart -->
    <div v-if="!loading && stats.message_trend.length > 0" class="trend-section">
      <NCard :bordered="false" class="trend-card">
        <div class="trend-header">
          <span class="trend-title">Message Trend</span>
          <span class="trend-subtitle">Last 7 days</span>
        </div>
        <SparklineChart :data="stats.message_trend" height="160px" />
      </NCard>
    </div>

    <!-- Status Wall -->
    <div v-if="!loading" class="status-wall">
      <NCard :bordered="false" class="wall-card">
        <div class="wall-title">Running Workflows</div>
        <div v-if="stats.running_workflows.length === 0" class="wall-empty">No active workflows</div>
        <div
          v-for="wf in stats.running_workflows"
          :key="wf.id"
          class="wall-item"
          @click="router.push(`/workflows/${wf.id}/edit`)"
        >
          <StatusBadge status="online" />
          <span class="wall-name">{{ wf.name }}</span>
          <span v-if="wf.last_run_at" class="wall-meta">{{ wf.last_run_at }}</span>
        </div>
      </NCard>

      <NCard :bordered="false" class="wall-card">
        <div class="wall-title">Cron Status</div>
        <div v-if="stats.cron_warnings.length === 0" class="wall-empty">No cron jobs</div>
        <div
          v-for="cj in stats.cron_warnings"
          :key="cj.id"
          class="wall-item"
          @click="router.push('/cron')"
        >
          <StatusBadge :status="cronStatus(cj.status)" />
          <span class="wall-name">{{ cj.name }}</span>
          <span v-if="cj.last_run_at" class="wall-meta">{{ cj.last_run_at }}</span>
        </div>
      </NCard>
    </div>
  </PageLayout>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-8);
}

.trend-section {
  margin-bottom: var(--space-8);
}
.trend-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.trend-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.trend-title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-primary);
}
.trend-subtitle {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.status-wall {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
.wall-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.wall-title {
  font-size: var(--text-base);
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}
.wall-empty {
  font-size: var(--text-sm);
  color: var(--text-muted);
}
.wall-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: background 150ms;
}
.wall-item:hover {
  background: var(--bg-muted);
}
.wall-name {
  font-size: var(--text-sm);
  color: var(--text-primary);
  flex: 1;
}
.wall-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

@media (max-width: 1023px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .status-wall {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 767px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
