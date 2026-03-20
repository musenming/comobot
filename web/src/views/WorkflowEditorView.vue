<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, useVueFlow, Position } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import {
  NButton, NSpace, NDrawer, NDrawerContent, NForm, NFormItem,
  NInput, NSelect, NInputNumber, useMessage
} from 'naive-ui'
import { useBreakpoints } from '@vueuse/core'
import api from '../api/client'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const message = useMessage()
const workflowId = computed(() => route.params.id ? Number(route.params.id) : null)
const workflowName = ref(t('workflowEditor.newWorkflow'))
const workflowDescription = ref('')

const breakpoints = useBreakpoints({ md: 768 })
const isMobile = breakpoints.smaller('md')

const NODE_TYPES = [
  { value: 'trigger', label: t('workflowEditor.trigger'), icon: '⚡', color: '#2563EB', desc: t('workflowEditor.startPoint') },
  { value: 'llm_call', label: t('workflowEditor.llmCall'), icon: '◆', color: '#8B5CF6', desc: t('workflowEditor.aiModelCall') },
  { value: 'tool', label: t('workflowEditor.tool'), icon: '⚙', color: '#F59E0B', desc: t('workflowEditor.externalAction') },
  { value: 'condition', label: t('workflowEditor.condition'), icon: '◇', color: '#EAB308', desc: t('workflowEditor.branchLogic') },
  { value: 'response', label: t('workflowEditor.response'), icon: '◈', color: '#22C55E', desc: t('workflowEditor.sendReply') },
  { value: 'delay', label: t('workflowEditor.delay'), icon: '◷', color: '#6B7280', desc: t('workflowEditor.waitTimer') },
  { value: 'subagent', label: t('workflowEditor.subAgent'), icon: '◎', color: '#EC4899', desc: t('workflowEditor.spawnAgent') },
]

function getNodeColor(type: string) {
  return NODE_TYPES.find(t => t.value === type)?.color || '#666'
}

function getNodeLabel(type: string) {
  const nt = NODE_TYPES.find(t => t.value === type)
  return nt ? `${nt.icon} ${nt.label}` : type
}

const { addNodes, addEdges, onConnect, removeNodes, removeEdges, getNodes, getEdges } = useVueFlow({
  defaultEdgeOptions: { animated: true, style: { stroke: 'var(--text-muted, #555)' } },
})

const showDrawer = ref(false)
const selectedNode = ref<any>(null)
const nodeForm = ref<Record<string, any>>({})
const showNodePanel = ref(true)

function onNodeClick({ node }: { node: any }) {
  selectedNode.value = node
  nodeForm.value = { ...node.data }
  showDrawer.value = true
}

function saveNodeConfig() {
  if (selectedNode.value) {
    const node = getNodes.value.find((n: any) => n.id === selectedNode.value.id)
    if (node) {
      node.data = { ...nodeForm.value }
    }
  }
  showDrawer.value = false
}

onConnect((params) => {
  addEdges([{
    id: `e-${params.source}-${params.target}`,
    source: params.source as string,
    target: params.target as string,
    animated: true,
    style: { stroke: 'var(--text-muted, #555)' },
  }])
})

let nodeCounter = 0

function addNode(type: string) {
  nodeCounter++
  const id = `${type}-${nodeCounter}`
  const x = 250 + Math.random() * 200
  const y = 100 + (getNodes.value.length) * 120

  const defaultData: Record<string, any> = { label: getNodeLabel(type) }

  if (type === 'trigger') {
    defaultData.trigger_type = 'message'
  } else if (type === 'llm_call') {
    defaultData.model = ''
    defaultData.system_prompt = ''
    defaultData.user_message = '{{trigger.message}}'
    defaultData.temperature = 0.7
    defaultData.max_tokens = 2000
  } else if (type === 'tool') {
    defaultData.tool_type = 'http_request'
    defaultData.url = ''
    defaultData.method = 'GET'
  } else if (type === 'condition') {
    defaultData.expression = ''
  } else if (type === 'response') {
    defaultData.content = '{{llm.response}}'
    defaultData.channel = '{{trigger.channel}}'
    defaultData.chat_id = '{{trigger.chat_id}}'
  } else if (type === 'delay') {
    defaultData.delay_seconds = 1
  } else if (type === 'subagent') {
    defaultData.task = ''
    defaultData.max_iterations = 5
  }

  const color = getNodeColor(type)
  addNodes([{
    id,
    type: 'default',
    position: { x, y },
    data: defaultData,
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    style: {
      background: color,
      color: '#fff',
      border: `2px solid ${color}`,
      borderRadius: '10px',
      padding: '10px 16px',
      fontSize: '13px',
      fontWeight: '500',
      minWidth: '150px',
      boxShadow: `0 2px 8px ${color}33`,
    },
    label: getNodeLabel(type),
    class: `node-${type}`,
  }])
}

function deleteNode() {
  if (!selectedNode.value) return
  const id = selectedNode.value.id
  const edgeIds = getEdges.value
    .filter((e: any) => e.source === id || e.target === id)
    .map((e: any) => e.id)
  removeEdges(edgeIds)
  removeNodes([id])
  showDrawer.value = false
  selectedNode.value = null
}

async function saveWorkflow() {
  const definition = {
    nodes: getNodes.value.map((n: any) => ({
      id: n.id,
      type: n.id.split('-')[0],
      position: n.position,
      data: n.data,
    })),
    edges: getEdges.value.map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
    })),
  }

  try {
    if (workflowId.value) {
      await api.put(`/workflows/${workflowId.value}`, {
        name: workflowName.value,
        description: workflowDescription.value,
        definition,
      })
      message.success(t('workflowEditor.saved'))
    } else {
      const { data } = await api.post('/workflows', {
        name: workflowName.value,
        description: workflowDescription.value,
        definition,
      })
      message.success(t('workflowEditor.createdMsg'))
      router.replace(`/workflows/${data.id}/edit`)
    }
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('workflowEditor.failedSave'))
  }
}

async function loadWorkflow() {
  if (!workflowId.value) return
  try {
    const { data } = await api.get(`/workflows/${workflowId.value}`)
    workflowName.value = data.name
    workflowDescription.value = data.description || ''
    const def = data.definition || {}
    const nodes = (def.nodes || []).map((n: any) => {
      const color = getNodeColor(n.type)
      return {
        id: n.id,
        type: 'default',
        position: n.position || { x: 0, y: 0 },
        data: n.data || {},
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        label: getNodeLabel(n.type),
        style: {
          background: color,
          color: '#fff',
          border: `2px solid ${color}`,
          borderRadius: '10px',
          padding: '10px 16px',
          fontSize: '13px',
          fontWeight: '500',
          minWidth: '150px',
          boxShadow: `0 2px 8px ${color}33`,
        },
      }
    })
    const edges = (def.edges || []).map((e: any) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: true,
      style: { stroke: 'var(--text-muted, #555)' },
    }))

    if (nodes.length) addNodes(nodes)
    if (edges.length) addEdges(edges)
    nodeCounter = nodes.length
  } catch {
    message.error(t('workflowEditor.failedLoad'))
  }
}

onMounted(loadWorkflow)
</script>

<template>
  <!-- Mobile guard -->
  <div v-if="isMobile" class="mobile-guard">
    <div class="mobile-guard-content">
      <span class="mobile-guard-icon">🖥</span>
      <h2>{{ t('workflowEditor.desktopRequired') }}</h2>
      <p>{{ t('workflowEditor.desktopRequiredDesc') }}</p>
      <NButton @click="router.push('/workflows')">{{ t('workflowEditor.backToWorkflows') }}</NButton>
    </div>
  </div>

  <div v-else class="editor-container">
    <!-- Toolbar -->
    <div class="editor-toolbar">
      <NSpace align="center">
        <NButton text @click="router.push('/workflows')" class="back-btn">{{ t('workflowEditor.back') }}</NButton>
        <NInput v-model:value="workflowName" :placeholder="t('workflowEditor.workflowName')" size="small" style="width: 200px;" />
      </NSpace>
      <NSpace>
        <NButton size="small" @click="showNodePanel = !showNodePanel">
          {{ showNodePanel ? t('workflowEditor.hideNodes') : t('workflowEditor.showNodes') }}
        </NButton>
        <NButton type="primary" size="small" @click="saveWorkflow">{{ t('common.save') }}</NButton>
      </NSpace>
    </div>

    <div class="editor-body">
      <!-- Node Panel -->
      <Transition name="panel-slide">
        <div v-if="showNodePanel" class="node-panel">
          <div class="panel-title">{{ t('workflowEditor.nodes') }}</div>
          <div
            v-for="nt in NODE_TYPES"
            :key="nt.value"
            class="node-type-card"
            :style="{ borderLeftColor: nt.color }"
            @click="addNode(nt.value)"
          >
            <span class="nt-icon">{{ nt.icon }}</span>
            <div class="nt-info">
              <span class="nt-name">{{ nt.label }}</span>
              <span class="nt-desc">{{ nt.desc }}</span>
            </div>
          </div>
        </div>
      </Transition>

      <!-- Canvas -->
      <div class="canvas-wrapper">
        <VueFlow
          :default-zoom="1"
          :min-zoom="0.2"
          :max-zoom="2"
          @node-click="onNodeClick"
          fit-view-on-init
        >
          <Background :gap="20" :size="1" pattern-color="var(--bg-muted, #1a1a1a)" />
          <Controls position="bottom-right" />
        </VueFlow>
      </div>
    </div>

    <!-- Config Drawer -->
    <NDrawer v-model:show="showDrawer" :width="320" placement="right" :mask-closable="true">
      <NDrawerContent :title="selectedNode?.label || 'Node Config'">
        <NForm v-if="selectedNode" label-placement="top">
          <template v-if="selectedNode.id.startsWith('trigger')">
            <NFormItem :label="t('workflowEditor.triggerType')">
              <NSelect
                v-model:value="nodeForm.trigger_type"
                :options="[
                  { label: t('workflowEditor.message'), value: 'message' },
                  { label: t('workflowEditor.cron'), value: 'cron' },
                  { label: t('workflowEditor.webhook'), value: 'webhook' },
                  { label: t('workflowEditor.manual'), value: 'manual' },
                ]"
              />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('llm_call')">
            <NFormItem :label="t('workflowEditor.model')">
              <NInput v-model:value="nodeForm.model" :placeholder="t('workflowEditor.modelPlaceholder')" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.systemPrompt')">
              <NInput v-model:value="nodeForm.system_prompt" type="textarea" :rows="3" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.userMessage')">
              <NInput v-model:value="nodeForm.user_message" type="textarea" :rows="2" placeholder="{{trigger.message}}" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.temperature')">
              <NInputNumber v-model:value="nodeForm.temperature" :min="0" :max="2" :step="0.1" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.maxTokens')">
              <NInputNumber v-model:value="nodeForm.max_tokens" :min="1" :max="128000" />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('tool')">
            <NFormItem :label="t('workflowEditor.toolType')">
              <NSelect
                v-model:value="nodeForm.tool_type"
                :options="[
                  { label: t('workflowEditor.httpRequest'), value: 'http_request' },
                  { label: t('workflowEditor.shellCommand'), value: 'shell' },
                  { label: t('workflowEditor.fileRead'), value: 'file_read' },
                ]"
              />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.url')" v-if="nodeForm.tool_type === 'http_request'">
              <NInput v-model:value="nodeForm.url" placeholder="https://..." />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.method')" v-if="nodeForm.tool_type === 'http_request'">
              <NSelect v-model:value="nodeForm.method" :options="['GET','POST','PUT','DELETE'].map(m => ({ label: m, value: m }))" />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('condition')">
            <NFormItem :label="t('workflowEditor.expression')">
              <NInput v-model:value="nodeForm.expression" placeholder="{{trigger.channel}} == telegram" />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('response')">
            <NFormItem :label="t('workflowEditor.content')">
              <NInput v-model:value="nodeForm.content" type="textarea" :rows="3" placeholder="{{llm.response}}" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.channel')">
              <NInput v-model:value="nodeForm.channel" placeholder="{{trigger.channel}}" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.chatId')">
              <NInput v-model:value="nodeForm.chat_id" placeholder="{{trigger.chat_id}}" />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('delay')">
            <NFormItem :label="t('workflowEditor.delaySeconds')">
              <NInputNumber v-model:value="nodeForm.delay_seconds" :min="0" />
            </NFormItem>
          </template>

          <template v-if="selectedNode.id.startsWith('subagent')">
            <NFormItem :label="t('workflowEditor.taskDescription')">
              <NInput v-model:value="nodeForm.task" type="textarea" :rows="3" />
            </NFormItem>
            <NFormItem :label="t('workflowEditor.maxIterations')">
              <NInputNumber v-model:value="nodeForm.max_iterations" :min="1" :max="50" />
            </NFormItem>
          </template>

          <NSpace justify="space-between" style="margin-top: 16px;">
            <NButton type="error" size="small" ghost @click="deleteNode">{{ t('common.delete') }}</NButton>
            <NSpace>
              <NButton size="small" @click="showDrawer = false">{{ t('common.cancel') }}</NButton>
              <NButton type="primary" size="small" @click="saveNodeConfig">{{ t('common.apply') }}</NButton>
            </NSpace>
          </NSpace>
        </NForm>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style>
.editor-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
}
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-2) var(--space-4);
  border-bottom: 1px solid var(--border);
  background: var(--bg-subtle);
}
.back-btn {
  color: var(--text-secondary) !important;
}
.editor-body {
  flex: 1;
  display: flex;
  position: relative;
  overflow: hidden;
}

/* Node Panel */
.node-panel {
  width: 180px;
  border-right: 1px solid var(--border);
  background: var(--bg-subtle);
  padding: var(--space-3);
  overflow-y: auto;
  flex-shrink: 0;
}
.panel-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
  padding: 0 var(--space-2);
}
.node-type-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  border-left: 3px solid transparent;
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 150ms;
}
.node-type-card:hover {
  background: var(--bg-muted);
}
.nt-icon {
  font-size: 16px;
  flex-shrink: 0;
}
.nt-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.nt-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}
.nt-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: width 200ms var(--ease-default), opacity 200ms;
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  width: 0;
  opacity: 0;
}

/* Canvas */
.canvas-wrapper {
  flex: 1;
  position: relative;
}
.vue-flow {
  background: var(--bg-base);
}
.vue-flow__node {
  cursor: pointer;
}
.vue-flow__edge-path {
  stroke: var(--text-muted, #555);
}
.vue-flow__controls {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.vue-flow__controls button {
  background: var(--surface);
  color: var(--text-secondary);
  border-bottom-color: var(--border);
}
.vue-flow__controls button:hover {
  background: var(--bg-muted);
}

/* Mobile Guard */
.mobile-guard {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-base);
  padding: var(--space-6);
}
.mobile-guard-content {
  text-align: center;
  max-width: 320px;
}
.mobile-guard-icon {
  font-size: 48px;
  display: block;
  margin-bottom: var(--space-4);
}
.mobile-guard-content h2 {
  font-size: var(--text-lg);
  color: var(--text-primary);
  margin: 0 0 var(--space-3);
}
.mobile-guard-content p {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--space-6);
}
</style>
