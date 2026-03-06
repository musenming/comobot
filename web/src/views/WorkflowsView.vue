<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NModal, NForm, NFormItem, NInput, NSelect, NSpace, useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import WorkflowCard from '../components/WorkflowCard.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const router = useRouter()
const message = useMessage()
const loading = ref(true)
const workflows = ref<any[]>([])
const templates = ref<any[]>([])
const showModeModal = ref(false)
const showTemplateModal = ref(false)
const selectedTemplate = ref<string | null>(null)
const templateForm = ref<Record<string, string>>({})
const workflowName = ref('')

async function loadWorkflows() {
  try {
    const { data } = await api.get('/workflows')
    workflows.value = data
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

async function loadTemplates() {
  try {
    const { data } = await api.get('/workflows/templates')
    templates.value = data
  } catch {
    // empty
  }
}

async function toggleWorkflow(wf: any) {
  try {
    await api.put(`/workflows/${wf.id}`, { enabled: !wf.enabled })
    await loadWorkflows()
  } catch {
    message.error('Failed to update workflow')
  }
}

async function duplicateWorkflow(wf: any) {
  try {
    await api.post(`/workflows/${wf.id}/duplicate`)
    message.success('Workflow duplicated')
    await loadWorkflows()
  } catch {
    message.error('Failed to duplicate')
  }
}

async function runWorkflow(wf: any) {
  try {
    await api.post(`/workflows/${wf.id}/run`)
    message.success('Workflow triggered')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to run')
  }
}

async function deleteWorkflow(wf: any) {
  try {
    await api.delete(`/workflows/${wf.id}`)
    message.success('Workflow deleted')
    await loadWorkflows()
  } catch {
    message.error('Failed to delete')
  }
}

function openNew() {
  showModeModal.value = true
}

function chooseTemplate() {
  showModeModal.value = false
  selectedTemplate.value = null
  templateForm.value = {}
  workflowName.value = ''
  showTemplateModal.value = true
}

function chooseAdvanced() {
  showModeModal.value = false
  router.push('/workflows/new')
}

function onTemplateSelect(id: string) {
  selectedTemplate.value = id
  const tpl = templates.value.find((t: any) => t.id === id)
  if (tpl) {
    templateForm.value = {}
    for (const p of tpl.params) {
      templateForm.value[p.key] = p.default || ''
    }
    workflowName.value = tpl.name
  }
}

async function createFromTemplate() {
  if (!selectedTemplate.value || !workflowName.value) {
    message.warning('Please select a template and enter a name')
    return
  }
  try {
    await api.post('/workflows/from-template', {
      template_id: selectedTemplate.value,
      name: workflowName.value,
      params: templateForm.value,
    })
    message.success('Workflow created')
    showTemplateModal.value = false
    await loadWorkflows()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to create workflow')
  }
}

onMounted(() => {
  loadWorkflows()
  loadTemplates()
})
</script>

<template>
  <PageLayout title="Createflow" description="Build and manage your automation workflows">
    <template #actions>
      <NButton type="primary" @click="openNew">+ New Workflow</NButton>
    </template>

    <div v-if="loading" class="wf-grid">
      <SkeletonCard v-for="i in 3" :key="i" height="200px" />
    </div>
    <template v-else-if="workflows.length === 0">
      <EmptyState icon="⚡" title="No workflows yet" description="Create your first workflow to automate tasks.">
        <NButton type="primary" @click="openNew">+ New Workflow</NButton>
      </EmptyState>
    </template>
    <div v-else class="wf-grid">
      <WorkflowCard
        v-for="wf in workflows"
        :key="wf.id"
        :workflow="wf"
        @edit="router.push(`/workflows/${wf.id}/edit`)"
        @toggle="toggleWorkflow(wf)"
        @duplicate="duplicateWorkflow(wf)"
        @run="runWorkflow(wf)"
        @delete="deleteWorkflow(wf)"
      />
    </div>

    <!-- Mode Selection Modal -->
    <NModal v-model:show="showModeModal" preset="card" title="Create Workflow" style="width: 400px;">
      <div class="mode-grid">
        <div class="mode-option" @click="chooseTemplate">
          <div class="mode-icon">📋</div>
          <div class="mode-label">Template</div>
          <div class="mode-desc">Quick start with presets</div>
        </div>
        <div class="mode-option" @click="chooseAdvanced">
          <div class="mode-icon">🎨</div>
          <div class="mode-label">Advanced</div>
          <div class="mode-desc">Custom flow editor</div>
        </div>
      </div>
    </NModal>

    <!-- Template Modal -->
    <NModal v-model:show="showTemplateModal" preset="card" title="Create from Template" style="width: 520px;">
      <NForm>
        <NFormItem label="Template">
          <NSelect
            :value="selectedTemplate"
            :options="templates.map((t: any) => ({ label: t.name, value: t.id }))"
            placeholder="Select a template"
            @update:value="onTemplateSelect"
          />
        </NFormItem>
        <NFormItem label="Workflow Name">
          <NInput v-model:value="workflowName" placeholder="Name" />
        </NFormItem>
        <template v-if="selectedTemplate">
          <NFormItem v-for="p in templates.find((t: any) => t.id === selectedTemplate)?.params" :key="p.key" :label="p.label">
            <NInput v-model:value="templateForm[p.key]" :placeholder="p.default" :type="p.type === 'textarea' ? 'textarea' : 'text'" />
          </NFormItem>
        </template>
        <NSpace justify="end">
          <NButton @click="showTemplateModal = false">Cancel</NButton>
          <NButton type="primary" @click="createFromTemplate">Create</NButton>
        </NSpace>
      </NForm>
    </NModal>
  </PageLayout>
</template>

<style scoped>
.wf-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}
.mode-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}
.mode-option {
  background: var(--bg-muted);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  text-align: center;
  cursor: pointer;
  transition: border-color 200ms, background 200ms;
}
.mode-option:hover {
  border-color: var(--text-muted);
  background: var(--surface);
}
.mode-icon {
  font-size: 32px;
  margin-bottom: var(--space-3);
}
.mode-label {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.mode-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: var(--space-1);
}

@media (max-width: 1023px) {
  .wf-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 767px) {
  .wf-grid { grid-template-columns: 1fr; }
}
</style>
