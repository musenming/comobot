<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageLayout from '../components/PageLayout.vue'
import ChatBubble from '../components/ChatBubble.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const sessions = ref<any[]>([])
const selectedKey = ref<string | null>(null)
const messages = ref<any[]>([])
const loadingMessages = ref(false)

async function loadSessions() {
  try {
    const { data } = await api.get('/sessions')
    sessions.value = data
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

async function selectSession(key: string) {
  selectedKey.value = key
  router.replace(`/sessions/${encodeURIComponent(key)}`)
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

onMounted(async () => {
  await loadSessions()
  const key = route.params.key as string
  if (key && sessions.value.length > 0) {
    await selectSession(decodeURIComponent(key))
  } else if (sessions.value.length > 0) {
    await selectSession(sessions.value[0].session_key)
  }
})
</script>

<template>
  <PageLayout title="Sessions" description="View conversation history">
    <div v-if="loading" class="sessions-layout">
      <div class="session-list">
        <SkeletonCard v-for="i in 5" :key="i" :lines="1" />
      </div>
      <div class="session-detail">
        <SkeletonCard :lines="3" />
      </div>
    </div>

    <template v-else-if="sessions.length === 0">
      <EmptyState icon="◎" title="No sessions yet" description="Sessions will appear here once users start chatting." />
    </template>

    <div v-else class="sessions-layout">
      <!-- Session List -->
      <div class="session-list">
        <div
          v-for="s in sessions"
          :key="s.session_key"
          class="session-item"
          :class="{ active: selectedKey === s.session_key }"
          @click="selectSession(s.session_key)"
        >
          <div class="session-name">{{ s.session_key }}</div>
          <div class="session-meta">
            <span v-if="s.channel" class="session-channel">{{ s.channel }}</span>
            <span>{{ s.message_count || 0 }} msgs</span>
          </div>
          <div v-if="s.preview" class="session-preview">{{ s.preview }}</div>
        </div>
      </div>

      <!-- Message Detail -->
      <div class="session-detail">
        <template v-if="selectedKey">
          <div v-if="loadingMessages" class="detail-loading">
            <SkeletonCard :lines="3" />
          </div>
          <template v-else-if="messages.length === 0">
            <EmptyState title="No messages" description="This session has no messages." />
          </template>
          <div v-else class="message-flow">
            <ChatBubble
              v-for="msg in messages"
              :key="msg.id"
              :role="msg.role"
              :content="msg.content || ''"
              :tool-calls="msg.tool_calls"
              :created-at="msg.created_at"
            />
          </div>
        </template>
        <template v-else>
          <EmptyState title="Select a session" description="Choose a session from the list to view messages." />
        </template>
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.sessions-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: var(--space-4);
  min-height: 60vh;
}
.session-list {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  overflow-y: auto;
  max-height: 75vh;
}
.session-item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 150ms;
}
.session-item:hover {
  background: var(--bg-muted);
}
.session-item.active {
  background: var(--bg-muted);
  border-left: 2px solid var(--text-primary);
}
.session-name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 2px;
}
.session-channel {
  text-transform: capitalize;
}
.session-preview {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-detail {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  padding: var(--space-6);
  overflow-y: auto;
  max-height: 75vh;
}
.message-flow {
  display: flex;
  flex-direction: column;
}

@media (max-width: 767px) {
  .sessions-layout {
    grid-template-columns: 1fr;
  }
  .session-list {
    max-height: 40vh;
  }
}
</style>
