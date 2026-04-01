<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { NTabs, NTabPane, NButton, NInput, NTag, NPopconfirm } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import { useI18n } from '../composables/useI18n'
import ChatBubble from '../components/ChatBubble.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const { t } = useI18n()

// --- ComoBrain tab ---
const canvasRef = ref<HTMLCanvasElement | null>(null)
let animId = 0

interface Particle {
  x: number; y: number; vx: number; vy: number; r: number
}

function initCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const rect = canvas.getBoundingClientRect()
  canvas.width = rect.width * dpr
  canvas.height = rect.height * dpr
  ctx.scale(dpr, dpr)

  const W = rect.width
  const H = rect.height
  const particles: Particle[] = Array.from({ length: 40 }, () => ({
    x: Math.random() * W,
    y: Math.random() * H,
    vx: (Math.random() - 0.5) * 0.5,
    vy: (Math.random() - 0.5) * 0.5,
    r: Math.random() * 2 + 1,
  }))

  function draw() {
    ctx!.clearRect(0, 0, W, H)
    ctx!.strokeStyle = 'rgba(128, 128, 128, 0.15)'
    ctx!.lineWidth = 1
    for (let i = 0; i < particles.length; i++) {
      const pi = particles[i]!
      for (let j = i + 1; j < particles.length; j++) {
        const pj = particles[j]!
        const dx = pi.x - pj.x
        const dy = pi.y - pj.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 120) {
          ctx!.beginPath()
          ctx!.moveTo(pi.x, pi.y)
          ctx!.lineTo(pj.x, pj.y)
          ctx!.stroke()
        }
      }
    }
    for (const p of particles) {
      ctx!.beginPath()
      ctx!.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx!.fillStyle = 'rgba(128, 128, 128, 0.5)'
      ctx!.fill()
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > W) p.vx *= -1
      if (p.y < 0 || p.y > H) p.vy *= -1
    }
    animId = requestAnimationFrame(draw)
  }
  draw()
}

// --- Sessions tab ---
const sessions = ref<any[]>([])
const selectedKey = ref<string | null>(null)
const messages = ref<any[]>([])
const loadingSessions = ref(true)
const loadingMessages = ref(false)

async function loadSessions() {
  try {
    const { data } = await api.get('/sessions')
    sessions.value = data
  } catch {
    // empty
  } finally {
    loadingSessions.value = false
  }
}

async function selectSession(key: string) {
  selectedKey.value = key
  loadingMessages.value = true
  try {
    const { data } = await api.get(`/sessions/${encodeURIComponent(key)}/messages`)
    messages.value = data
  } catch {
    messages.value = []
  } finally {
    loadingMessages.value = false
  }
}

// --- Episodic Memory tab ---
interface EpisodicMemory {
  id: string
  type: string
  content: string
  confidence: number
  source_session: string
  source_channel: string
  tags: string[]
  created_at: string
  last_accessed_at: string | null
  access_count: number
  status: string
}

interface EpisodicStats {
  total: number
  by_type: Record<string, number>
  most_used: Array<{ id: string; content: string; access_count: number }>
}

const memories = ref<EpisodicMemory[]>([])
const epStats = ref<EpisodicStats>({ total: 0, by_type: {}, most_used: [] })
const epLoading = ref(false)
const epTypeFilter = ref<string | null>(null)
const epStatusFilter = ref('active')
const epOffset = ref(0)
const epHasMore = ref(false)
const epExpandedId = ref<string | null>(null)
const epEditContent = ref('')
const epEditTags = ref('')
const epSaving = ref(false)

const typeFilters = [
  { key: null, label: () => t('memory.filter.all') },
  { key: 'task', label: () => t('memory.types.task') },
  { key: 'fact', label: () => t('memory.types.fact') },
  { key: 'preference', label: () => t('memory.types.preference') },
  { key: 'feedback', label: () => t('memory.types.feedback') },
]

const typeBorderColors: Record<string, string> = {
  task: 'var(--accent-blue)',
  fact: 'var(--accent-green)',
  preference: 'var(--accent-yellow)',
  feedback: '#9333ea',
}

const typeBadgeStyles: Record<string, { bg: string; fg: string }> = {
  task: { bg: 'rgba(37, 99, 235, 0.08)', fg: 'var(--accent-blue)' },
  fact: { bg: 'rgba(22, 163, 74, 0.08)', fg: 'var(--accent-green)' },
  preference: { bg: 'rgba(202, 138, 4, 0.08)', fg: 'var(--accent-yellow)' },
  feedback: { bg: 'rgba(147, 51, 234, 0.08)', fg: '#9333ea' },
}

async function loadEpisodicMemories(reset = true) {
  if (reset) {
    epOffset.value = 0
    memories.value = []
  }
  epLoading.value = true
  try {
    const params: any = { limit: 30, offset: epOffset.value, status: epStatusFilter.value }
    if (epTypeFilter.value) params.type = epTypeFilter.value
    const { data } = await api.get('/memory/episodic', { params })
    if (reset) {
      memories.value = data
    } else {
      memories.value.push(...data)
    }
    epHasMore.value = data.length >= 30
    epOffset.value += data.length
  } catch {
    // empty
  } finally {
    epLoading.value = false
  }
}

async function loadEpisodicStats() {
  try {
    const { data } = await api.get('/memory/episodic/stats')
    epStats.value = data
  } catch {
    // empty
  }
}

function toggleExpand(mem: EpisodicMemory) {
  if (epExpandedId.value === mem.id) {
    epExpandedId.value = null
  } else {
    epExpandedId.value = mem.id
    epEditContent.value = mem.content
    epEditTags.value = mem.tags.join(', ')
  }
}

async function saveMemory(mem: EpisodicMemory) {
  epSaving.value = true
  try {
    const tags = epEditTags.value.split(',').map(t => t.trim()).filter(Boolean)
    await api.put(`/memory/episodic/${mem.id}`, { content: epEditContent.value, tags })
    mem.content = epEditContent.value
    mem.tags = tags
    epExpandedId.value = null
  } catch {
    // empty
  } finally {
    epSaving.value = false
  }
}

async function archiveMemory(id: string) {
  try {
    await api.delete(`/memory/episodic/${id}`)
    memories.value = memories.value.filter(m => m.id !== id)
    if (epStats.value.total > 0) epStats.value.total--
  } catch {
    // empty
  }
}

function formatDate(dateStr: string): string {
  if (!dateStr) return ''
  try {
    const d = new Date(dateStr)
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}

function confidencePercent(val: number): string {
  return `${Math.round(val * 100)}%`
}

const statsBarSegments = computed(() => {
  const byType = epStats.value.by_type
  const total = epStats.value.total || 1
  return ['task', 'fact', 'preference', 'feedback']
    .filter(t => (byType[t] || 0) > 0)
    .map(t => ({
      type: t,
      count: byType[t] || 0,
      pct: ((byType[t] || 0) / total) * 100,
      color: typeBorderColors[t] || 'var(--text-muted)',
    }))
})

watch([epTypeFilter, epStatusFilter], () => {
  loadEpisodicMemories(true)
})

// --- Lifecycle ---
onMounted(() => {
  loadSessions()
  setTimeout(initCanvas, 100)
  loadEpisodicMemories()
  loadEpisodicStats()
})

onUnmounted(() => {
  if (animId) cancelAnimationFrame(animId)
})
</script>

<template>
  <PageLayout :title="t('memory.title')">
    <NTabs type="segment" animated>
      <NTabPane name="brain" :tab="t('memory.comoBrain')">
        <div class="brain-container">
          <canvas ref="canvasRef" class="brain-canvas" />
          <div class="brain-overlay">
            <span class="brain-icon">&#x25D0;</span>
            <p>{{ t('memory.visualizationSoon') }}</p>
          </div>
        </div>
      </NTabPane>

      <!-- Episodic Memory tab -->
      <NTabPane name="episodic" :tab="t('memory.episodic')">
        <div class="ep-container">
          <!-- Stats bar -->
          <div class="ep-stats">
            <div class="ep-stats-total">
              <span class="ep-stats-num">{{ epStats.total }}</span>
              <span class="ep-stats-label">{{ t('memory.stats.total') }}</span>
            </div>
            <div v-if="statsBarSegments.length > 0" class="ep-stats-bar-wrap">
              <div class="ep-stats-bar">
                <div
                  v-for="seg in statsBarSegments"
                  :key="seg.type"
                  class="ep-stats-seg"
                  :style="{ width: `${seg.pct}%`, background: seg.color }"
                  :title="`${t(`memory.types.${seg.type}`)}: ${seg.count}`"
                />
              </div>
              <div class="ep-stats-legend">
                <span v-for="seg in statsBarSegments" :key="seg.type" class="ep-legend-item">
                  <span class="ep-legend-dot" :style="{ background: seg.color }" />
                  {{ t(`memory.types.${seg.type}`) }} {{ seg.count }}
                </span>
              </div>
            </div>
          </div>

          <!-- Filter chips -->
          <div class="ep-filters">
            <button
              v-for="f in typeFilters"
              :key="String(f.key)"
              class="ep-chip"
              :class="{ 'ep-chip--active': epTypeFilter === f.key }"
              @click="epTypeFilter = f.key"
            >
              <span v-if="f.key" class="ep-chip-dot" :style="{ background: typeBorderColors[f.key] || 'var(--text-muted)' }" />
              {{ f.label() }}
            </button>
            <span class="ep-filter-spacer" />
            <button
              class="ep-chip ep-chip-status"
              :class="{ 'ep-chip--active': epStatusFilter === 'active' }"
              @click="epStatusFilter = 'active'"
            >{{ t('memory.filter.active') }}</button>
            <button
              class="ep-chip ep-chip-status"
              :class="{ 'ep-chip--active': epStatusFilter === 'archived' }"
              @click="epStatusFilter = 'archived'"
            >{{ t('memory.filter.archived') }}</button>
          </div>

          <!-- Memory list -->
          <div class="ep-list">
            <div v-if="epLoading && memories.length === 0" class="ep-loading">
              {{ t('common.loading') }}
            </div>

            <EmptyState v-else-if="memories.length === 0" :message="t('memory.empty')" />

            <template v-else>
              <div
                v-for="mem in memories"
                :key="mem.id"
                class="ep-card"
                :class="{ 'ep-card--expanded': epExpandedId === mem.id }"
                :style="{ '--card-accent': typeBorderColors[mem.type] || 'var(--text-muted)' }"
              >
                <div class="ep-card-main" @click="toggleExpand(mem)">
                  <div class="ep-card-left">
                    <span
                      class="ep-type-badge"
                      :style="{
                        background: typeBadgeStyles[mem.type]?.bg || 'var(--bg-subtle)',
                        color: typeBadgeStyles[mem.type]?.fg || 'var(--text-muted)',
                      }"
                    >{{ t(`memory.types.${mem.type}`) }}</span>
                  </div>
                  <div class="ep-card-body">
                    <div class="ep-card-content">{{ mem.content }}</div>
                    <div class="ep-card-meta">
                      <span class="ep-card-id">{{ mem.id }}</span>
                      <span class="ep-card-date">{{ formatDate(mem.created_at) }}</span>
                      <span v-if="mem.tags.length > 0" class="ep-card-tags">
                        <NTag v-for="tag in mem.tags.slice(0, 3)" :key="tag" size="tiny" :bordered="false">{{ tag }}</NTag>
                        <span v-if="mem.tags.length > 3" class="ep-card-more">+{{ mem.tags.length - 3 }}</span>
                      </span>
                    </div>
                  </div>
                  <div class="ep-card-right">
                    <span class="ep-conf" :title="t('memory.confidence')">{{ confidencePercent(mem.confidence) }}</span>
                    <span class="ep-access" :title="t('memory.accessCount')">{{ mem.access_count }}x</span>
                  </div>
                </div>

                <!-- Expanded edit panel -->
                <Transition name="ep-expand">
                  <div v-if="epExpandedId === mem.id" class="ep-card-edit">
                    <div class="ep-edit-field">
                      <label class="ep-edit-label">Content</label>
                      <NInput
                        v-model:value="epEditContent"
                        type="textarea"
                        :autosize="{ minRows: 2, maxRows: 8 }"
                        size="small"
                      />
                    </div>
                    <div class="ep-edit-field">
                      <label class="ep-edit-label">{{ t('memory.tags') }}</label>
                      <NInput
                        v-model:value="epEditTags"
                        size="small"
                        placeholder="tag1, tag2, ..."
                      />
                    </div>
                    <div class="ep-edit-info">
                      <span v-if="mem.source_session">{{ t('memory.source') }}: {{ mem.source_session }}</span>
                      <span v-if="mem.last_accessed_at">{{ t('memory.lastAccessed') }}: {{ formatDate(mem.last_accessed_at) }}</span>
                    </div>
                    <div class="ep-edit-actions">
                      <NButton size="small" type="primary" :loading="epSaving" @click="saveMemory(mem)">
                        {{ t('memory.actions.edit') }}
                      </NButton>
                      <NPopconfirm @positive-click="archiveMemory(mem.id)">
                        <template #trigger>
                          <NButton size="small" type="warning" quaternary>
                            {{ t('memory.actions.archive') }}
                          </NButton>
                        </template>
                        {{ t('memory.confirmArchive') }}
                      </NPopconfirm>
                      <NButton size="small" quaternary @click="epExpandedId = null">
                        {{ t('common.cancel') }}
                      </NButton>
                    </div>
                  </div>
                </Transition>
              </div>

              <!-- Load more -->
              <div v-if="epHasMore" class="ep-load-more">
                <NButton size="small" :loading="epLoading" @click="loadEpisodicMemories(false)">
                  {{ t('common.loading') }}
                </NButton>
              </div>
            </template>
          </div>
        </div>
      </NTabPane>

      <NTabPane name="sessions" :tab="t('memory.sessions')">
        <div class="sessions-layout">
          <div class="sessions-list">
            <div v-if="loadingSessions" class="loading-text">{{ t('common.loading') }}</div>
            <div
              v-for="s in sessions"
              :key="s.session_key"
              class="session-item"
              :class="{ active: selectedKey === s.session_key }"
              @click="selectSession(s.session_key)"
            >
              <div class="session-key">{{ s.session_key }}</div>
              <div class="session-time">{{ s.created_at }}</div>
            </div>
            <EmptyState v-if="!loadingSessions && sessions.length === 0" :message="t('memory.noSessions')" />
          </div>
          <div class="sessions-detail">
            <template v-if="selectedKey">
              <div v-if="loadingMessages" class="loading-text">{{ t('memory.loadingMessages') }}</div>
              <div v-else class="messages-scroll">
                <ChatBubble
                  v-for="(msg, i) in messages"
                  :key="i"
                  :role="msg.role"
                  :content="msg.content"
                  :created-at="msg.created_at"
                />
              </div>
            </template>
            <EmptyState v-else :message="t('memory.selectSessionView')" />
          </div>
        </div>
      </NTabPane>

      <NTabPane name="knowledge" :tab="t('memory.knowledgeBase')">
        <div class="knowledge-container">
          <EmptyState :message="t('memory.knowledgeBaseSoon')" />
        </div>
      </NTabPane>
    </NTabs>
  </PageLayout>
</template>

<style scoped>
/* --- ComoBrain --- */
.brain-container {
  position: relative;
  height: 400px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-subtle);
}
.brain-canvas { width: 100%; height: 100%; }
.brain-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  pointer-events: none;
}
.brain-icon { font-size: 48px; opacity: 0.3; margin-bottom: var(--space-3); }

/* --- Sessions --- */
.sessions-layout { display: flex; gap: var(--space-4); height: calc(100vh - 280px); }
.sessions-list {
  width: 280px; flex-shrink: 0; overflow-y: auto;
  border-right: 1px solid var(--border); padding-right: var(--space-4);
}
.session-item {
  padding: var(--space-3); border-radius: var(--radius-md);
  cursor: pointer; margin-bottom: var(--space-1); transition: background 150ms;
}
.session-item:hover { background: var(--bg-muted); }
.session-item.active { background: var(--bg-muted); }
.session-key {
  font-size: var(--text-sm); font-weight: 500; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.session-time { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }
.sessions-detail { flex: 1; overflow-y: auto; }
.messages-scroll { padding: var(--space-4) 0; }
.loading-text { color: var(--text-muted); font-size: var(--text-sm); padding: var(--space-4); }
.knowledge-container { padding: var(--space-8) 0; }

/* --- Episodic Memory --- */
.ep-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-height: 300px;
}

/* Stats */
.ep-stats {
  display: flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-4) var(--space-5);
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.ep-stats-total {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 72px;
}
.ep-stats-num {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.ep-stats-label {
  font-size: 10px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 2px;
}
.ep-stats-bar-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ep-stats-bar {
  display: flex;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: var(--bg-muted);
}
.ep-stats-seg {
  min-width: 4px;
  transition: width 400ms var(--ease-default);
}
.ep-stats-legend {
  display: flex;
  gap: var(--space-4);
  font-size: 10px;
  color: var(--text-secondary);
}
.ep-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.ep-legend-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Filters */
.ep-filters {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.ep-filter-spacer { flex: 1; }
.ep-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 150ms var(--ease-default);
  font-family: inherit;
}
.ep-chip:hover {
  background: var(--bg-muted);
  border-color: var(--text-muted);
  transform: none;
}
.ep-chip--active {
  background: var(--text-primary);
  color: var(--bg-base);
  border-color: var(--text-primary);
}
.ep-chip--active:hover {
  background: var(--text-primary);
  color: var(--bg-base);
}
.ep-chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ep-chip--active .ep-chip-dot { opacity: 0.7; }

/* Memory list */
.ep-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ep-loading {
  padding: var(--space-6);
  text-align: center;
  color: var(--text-muted);
  font-size: var(--text-sm);
}

/* Memory card */
.ep-card {
  border: 1px solid var(--border);
  border-left: 3px solid var(--card-accent);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  background: var(--surface);
  transition: box-shadow 200ms var(--ease-default), border-color 200ms;
  overflow: hidden;
}
.ep-card:hover {
  box-shadow: var(--shadow-sm);
}
.ep-card--expanded {
  box-shadow: var(--shadow-md);
  border-color: color-mix(in srgb, var(--border) 60%, var(--card-accent) 40%);
}
.ep-card-main {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  min-height: 52px;
}
.ep-card-left {
  flex-shrink: 0;
  padding-top: 2px;
}
.ep-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.ep-card-body {
  flex: 1;
  min-width: 0;
}
.ep-card-content {
  font-size: var(--text-sm);
  color: var(--text-primary);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ep-card--expanded .ep-card-content {
  -webkit-line-clamp: unset;
}
.ep-card-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: 4px;
  flex-wrap: wrap;
}
.ep-card-id {
  font-family: 'SF Mono', 'Cascadia Code', 'JetBrains Mono', monospace;
  font-size: 9px;
  color: var(--text-muted);
  background: var(--bg-muted);
  padding: 1px 5px;
  border-radius: 3px;
}
.ep-card-date {
  font-size: 10px;
  color: var(--text-muted);
}
.ep-card-tags {
  display: flex;
  gap: 3px;
  align-items: center;
}
.ep-card-more {
  font-size: 9px;
  color: var(--text-muted);
}
.ep-card-right {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  padding-top: 2px;
}
.ep-conf {
  font-family: 'SF Mono', monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-green);
}
.ep-access {
  font-family: 'SF Mono', monospace;
  font-size: 9px;
  color: var(--text-muted);
}

/* Edit panel */
.ep-card-edit {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border);
  background: var(--bg-subtle);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ep-edit-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ep-edit-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}
.ep-edit-info {
  display: flex;
  gap: var(--space-4);
  font-size: 10px;
  color: var(--text-muted);
}
.ep-edit-actions {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

/* Expand transition */
.ep-expand-enter-active,
.ep-expand-leave-active {
  transition: all 250ms var(--ease-default);
  overflow: hidden;
}
.ep-expand-enter-from,
.ep-expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.ep-expand-enter-to,
.ep-expand-leave-from {
  opacity: 1;
  max-height: 500px;
}

/* Load more */
.ep-load-more {
  display: flex;
  justify-content: center;
  padding: var(--space-3);
}
</style>
