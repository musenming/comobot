<script setup lang="ts">
import { ref, h, onMounted, onUnmounted } from 'vue'
import { NButton, NSpace, NDrawer, NDrawerContent, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import DataTable from '../components/DataTable.vue'
import StatusBadge from '../components/StatusBadge.vue'
import CronExpressionInput from '../components/CronExpressionInput.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import api from '../api/client'

const message = useMessage()
const loading = ref(true)
const jobs = ref<any[]>([])
const drawerOpen = ref(false)
const editingId = ref<number | null>(null)
const deleteConfirm = ref(false)
const deleteTarget = ref<number | null>(null)
const now = ref(Date.now())
let tickTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let cronWs: WebSocket | null = null

const form = ref({
  name: '',
  expression: '',
  command: '',
  description: '',
})

// WebSocket for real-time cron updates
function connectCronWs() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  cronWs = new WebSocket(`${proto}//${location.host}/ws/cron`)
  cronWs.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data)
      if (data.type === 'ping') return
      if (data.type === 'job_added' || data.type === 'job_executed' || data.type === 'job_notification') {
        // Refresh job list when any cron event occurs
        loadJobs()
        if (data.type === 'job_notification' && data.message) {
          message.info(`Cron: ${data.job_name || 'Task'} completed`, { duration: 5000 })
        }
      }
    } catch {
      // ignore
    }
  }
  cronWs.onclose = () => {
    // Reconnect after 3s
    setTimeout(() => {
      if (tickTimer) connectCronWs()
    }, 3000)
  }
}

// Tick every second for countdown
onMounted(() => {
  tickTimer = setInterval(() => { now.value = Date.now() }, 1000)
  // Poll every 15s as fallback
  pollTimer = setInterval(loadJobs, 15000)
  connectCronWs()
})
onUnmounted(() => {
  if (tickTimer) clearInterval(tickTimer)
  if (pollTimer) clearInterval(pollTimer)
  tickTimer = null
  if (cronWs) {
    cronWs.onclose = null
    cronWs.close()
    cronWs = null
  }
})

function formatCountdown(nextRunAt: string | null): string {
  if (!nextRunAt) return '—'
  const target = new Date(nextRunAt).getTime()
  const diff = target - now.value
  if (diff <= 0) return 'Due now'
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ${minutes % 60}m`
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}

function parseScheduleDisplay(row: any): string {
  // The schedule column is a JSON string from the cron service
  if (row.schedule_display) return row.schedule_display
  if (row.expression) return row.expression
  try {
    const sched = typeof row.schedule === 'string' ? JSON.parse(row.schedule) : row.schedule
    if (sched?.kind === 'cron' && sched?.expr) return sched.expr
    if (sched?.kind === 'at' && sched?.atMs) {
      return new Date(sched.atMs).toLocaleString()
    }
    if (sched?.kind === 'every' && sched?.everyMs) {
      const sec = sched.everyMs / 1000
      if (sec < 60) return `every ${sec}s`
      if (sec < 3600) return `every ${Math.round(sec / 60)}m`
      return `every ${Math.round(sec / 3600)}h`
    }
  } catch {
    // fallback
  }
  return String(row.schedule || '—')
}

function parsePayloadSummary(row: any): string {
  if (row.command) return row.command
  try {
    const payload = typeof row.payload === 'string' ? JSON.parse(row.payload) : row.payload
    return payload?.message || ''
  } catch {
    return ''
  }
}

const columns = [
  {
    title: 'Status',
    key: 'enabled',
    width: 80,
    render: (row: any) => {
      // Disabled or completed (no next run) jobs show as offline
      const isOffline = !row.enabled || (!row.next_run_at && row.last_run_at)
      const st = isOffline ? 'offline' : (row.last_status === 'error' ? 'error' : 'online')
      return h(StatusBadge, { status: st })
    },
  },
  {
    title: 'Name',
    key: 'name',
    width: 160,
  },
  {
    title: 'Schedule',
    key: 'schedule',
    width: 140,
    render: (row: any) => parseScheduleDisplay(row),
  },
  {
    title: 'Task Summary',
    key: 'payload',
    ellipsis: { tooltip: true },
    render: (row: any) => {
      const summary = parsePayloadSummary(row)
      return summary.length > 60 ? summary.slice(0, 60) + '...' : summary || '—'
    },
  },
  {
    title: 'Next Run',
    key: 'next_run_at',
    width: 120,
    render: (row: any) => {
      const countdown = formatCountdown(row.next_run_at)
      return h('span', { style: countdown === 'Due now' ? 'color: var(--accent-green, #22c55e); font-weight: 500' : '' }, countdown)
    },
  },
  { title: 'Last Run', key: 'last_run_at', width: 140, render: (row: any) => row.last_run_at || '—' },
  {
    title: 'Actions',
    key: 'actions',
    width: 260,
    render: (row: any) => h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'small', quaternary: true, onClick: () => runJob(row.id) }, () => 'Run'),
      h(NButton, { size: 'small', quaternary: true, onClick: () => openEdit(row) }, () => 'Edit'),
      h(NButton, { size: 'small', quaternary: true, onClick: () => toggleJob(row.id) }, () => row.enabled ? 'Pause' : 'Resume'),
      h(NButton, { size: 'small', quaternary: true, type: 'error', onClick: () => confirmDelete(row.id) }, () => 'Delete'),
    ]),
  },
]

async function loadJobs() {
  try {
    const { data } = await api.get('/cron')
    jobs.value = data || []
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

function openNew() {
  editingId.value = null
  form.value = { name: '', expression: '', command: '', description: '' }
  drawerOpen.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.value = {
    name: row.name || '',
    expression: parseScheduleDisplay(row),
    command: parsePayloadSummary(row),
    description: row.description || '',
  }
  drawerOpen.value = true
}

async function saveJob() {
  if (!form.value.name || !form.value.expression) {
    message.warning('Name and expression are required')
    return
  }
  try {
    if (editingId.value) {
      await api.put(`/cron/${editingId.value}`, form.value)
      message.success('Job updated')
    } else {
      await api.post('/cron', form.value)
      message.success('Job created')
    }
    drawerOpen.value = false
    await loadJobs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to save')
  }
}

async function runJob(id: number) {
  try {
    await api.post(`/cron/${id}/run`)
    message.success('Job triggered')
    await loadJobs()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to run')
  }
}

async function toggleJob(id: number) {
  try {
    await api.put(`/cron/${id}/toggle`)
    await loadJobs()
  } catch {
    message.error('Failed to toggle')
  }
}

function confirmDelete(id: number) {
  deleteTarget.value = id
  deleteConfirm.value = true
}

async function handleDelete() {
  if (!deleteTarget.value) return
  try {
    await api.delete(`/cron/${deleteTarget.value}`)
    message.success('Job deleted')
    await loadJobs()
  } catch {
    message.error('Failed to delete')
  }
}

onMounted(loadJobs)
</script>

<template>
  <PageLayout title="Cron Jobs" description="Scheduled automation tasks">
    <template #actions>
      <NButton type="primary" @click="openNew">+ New Cron Job</NButton>
    </template>

    <DataTable
      :columns="columns"
      :data="jobs"
      :loading="loading"
      empty-icon="&#9719;"
      empty-title="No cron jobs"
      empty-description="Create scheduled tasks to automate your workflows."
    >
      <template #empty>
        <NButton type="primary" @click="openNew">+ New Cron Job</NButton>
      </template>
    </DataTable>

    <!-- Edit Drawer -->
    <NDrawer v-model:show="drawerOpen" :width="420" placement="right">
      <NDrawerContent :title="editingId ? 'Edit Cron Job' : 'New Cron Job'">
        <NForm label-placement="top">
          <NFormItem label="Name">
            <NInput v-model:value="form.name" placeholder="Daily summary" />
          </NFormItem>
          <NFormItem label="Cron Expression">
            <CronExpressionInput v-model:value="form.expression" />
          </NFormItem>
          <NFormItem label="Command / Task">
            <NInput v-model:value="form.command" type="textarea" :rows="3" placeholder="What to execute..." />
          </NFormItem>
          <NFormItem label="Description">
            <NInput v-model:value="form.description" placeholder="Optional description" />
          </NFormItem>
        </NForm>
        <template #footer>
          <NSpace justify="end">
            <NButton @click="drawerOpen = false">Cancel</NButton>
            <NButton type="primary" @click="saveJob">Save</NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-model:show="deleteConfirm"
      title="Delete Cron Job"
      description="This action cannot be undone. The cron job will be permanently deleted."
      danger
      @confirm="handleDelete"
    />
  </PageLayout>
</template>
