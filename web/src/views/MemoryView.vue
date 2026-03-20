<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { NTabs, NTabPane } from 'naive-ui'
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
    // Draw connections
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
    // Draw particles
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

onMounted(() => {
  loadSessions()
  // Delay canvas init to ensure DOM is ready
  setTimeout(initCanvas, 100)
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
.brain-container {
  position: relative;
  height: 400px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-subtle);
}
.brain-canvas {
  width: 100%;
  height: 100%;
}
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
.brain-icon {
  font-size: 48px;
  opacity: 0.3;
  margin-bottom: var(--space-3);
}

.sessions-layout {
  display: flex;
  gap: var(--space-4);
  height: calc(100vh - 280px);
}
.sessions-list {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
  border-right: 1px solid var(--border);
  padding-right: var(--space-4);
}
.session-item {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  margin-bottom: var(--space-1);
  transition: background 150ms;
}
.session-item:hover {
  background: var(--bg-muted);
}
.session-item.active {
  background: var(--bg-muted);
}
.session-key {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.sessions-detail {
  flex: 1;
  overflow-y: auto;
}
.messages-scroll {
  padding: var(--space-4) 0;
}
.loading-text {
  color: var(--text-muted);
  font-size: var(--text-sm);
  padding: var(--space-4);
}
.knowledge-container {
  padding: var(--space-8) 0;
}
</style>
