<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
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

const form = ref({
  name: '',
  expression: '',
  command: '',
  description: '',
})

const columns = [
  {
    title: 'Status',
    key: 'enabled',
    width: 100,
    render: (row: any) => h(StatusBadge, {
      status: row.enabled ? (row.last_status === 'failed' ? 'error' : 'online') : 'offline',
    }),
  },
  { title: 'Name', key: 'name' },
  { title: 'Schedule', key: 'expression' },
  { title: 'Last Run', key: 'last_run_at', render: (row: any) => row.last_run_at || '—' },
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
    expression: row.expression || '',
    command: row.command || '',
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
      empty-icon="◷"
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
