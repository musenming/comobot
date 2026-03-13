<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { NBadge } from 'naive-ui'
import api from '../api/client'

interface ChannelSession {
  session_key: string
  chat_id: string
  chat_label: string
  message_count: number
  last_message_at: string
  summary?: string
  last_message_preview?: string
}
interface Channel {
  channel_type: string
  display_name: string
  sessions: ChannelSession[]
}

interface SessionSelectMeta {
  key: string
  title: string
}

const props = defineProps<{ selectedKey?: string | null }>()
const emit = defineEmits<{
  select: [key: string]
  'select-meta': [meta: SessionSelectMeta]
}>()

const channels = ref<Channel[]>([])
const expanded = ref<Record<string, boolean>>({})
const loading = ref(true)

async function load() {
  try {
    const { data } = await api.get('/sessions/by-channel')
    channels.value = data.channels
    data.channels.forEach((c: Channel) => {
      expanded.value[c.channel_type] = true
    })
  } catch {
    // fallback to empty
  } finally {
    loading.value = false
  }
}

function toggle(type: string) {
  expanded.value[type] = !expanded.value[type]
}

function formatUpdatedAt(value?: string): string {
  if (!value) return 'Unknown time'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

function getSessionTitle(session: ChannelSession): string {
  return (session.summary || session.chat_label || session.chat_id || session.session_key).trim()
}

function getSessionPreview(session: ChannelSession): string {
  return (session.last_message_preview || '').trim() || '暂无消息内容'
}

function emitSessionMeta(session: ChannelSession) {
  emit('select-meta', {
    key: session.session_key,
    title: getSessionTitle(session),
  })
}

function selectSession(session: ChannelSession) {
  emit('select', session.session_key)
  emitSessionMeta(session)
}

watch(
  () => [props.selectedKey, channels.value] as const,
  ([selectedKey]) => {
    if (!selectedKey) return
    const selectedSession = channels.value
      .flatMap(channel => channel.sessions)
      .find(session => session.session_key === selectedKey)
    if (selectedSession) {
      emitSessionMeta(selectedSession)
    }
  },
  { deep: true, immediate: true },
)

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="channel-tree">
    <div class="tree-scroll">
      <div v-if="loading" class="tree-loading">Loading...</div>
      <div v-else-if="channels.length === 0" class="tree-empty">No sessions</div>
      <div v-for="channel in channels" :key="channel.channel_type" class="channel-group">
        <div class="channel-header" @click="toggle(channel.channel_type)">
          <span class="expand-icon">{{ expanded[channel.channel_type] ? '\u25BC' : '\u25B6' }}</span>
          <span class="channel-name">{{ channel.display_name }}</span>
          <n-badge :value="channel.sessions.length" :max="99" />
        </div>
        <div v-show="expanded[channel.channel_type]" class="session-list">
          <div
            v-for="s in channel.sessions"
            :key="s.session_key"
            class="session-item"
            :class="{ active: s.session_key === selectedKey }"
            @click="selectSession(s)"
          >
            <div class="session-item-top">
              <span class="session-title">{{ getSessionTitle(s) }}</span>
              <span class="session-time">{{ formatUpdatedAt(s.last_message_at) }}</span>
            </div>
            <div class="session-item-bottom">
              <span class="session-preview">{{ getSessionPreview(s) }}</span>
              <span class="msg-count">{{ s.message_count }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.channel-tree {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.tree-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  padding: var(--space-1) 0 var(--space-4) 0;
}
.tree-loading, .tree-empty {
  padding: var(--space-4) var(--space-3);
  color: var(--text-muted);
  font-size: var(--text-sm);
  text-align: left;
}
.channel-group {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 0 var(--space-2) var(--space-2);
  overflow: hidden;
}
.channel-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px var(--space-2);
  cursor: pointer;
  font-size: var(--text-base);
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #111;
  user-select: none;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-subtle) 96%, #fff 4%);
}
.channel-header:hover {
  background: color-mix(in srgb, var(--bg-muted) 65%, #fff 35%);
}
.expand-icon {
  font-size: 10px;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}
.channel-name {
  flex: 1;
}
.session-list {
  margin-top: 2px;
  padding-left: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 0;
}
.session-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px var(--space-3) 10px var(--space-2);
  cursor: pointer;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  border-radius: var(--radius-md);
  border-left: 2px solid transparent;
  transition: background 150ms var(--ease-default), border-color 150ms var(--ease-default), color 150ms var(--ease-default);
}
.session-item + .session-item {
  border-top: 1px solid color-mix(in srgb, var(--border) 88%, #9ca3af 12%);
}
.session-item:hover {
  background: color-mix(in srgb, var(--bg-muted) 80%, transparent);
  border-left-color: color-mix(in srgb, var(--accent-blue) 45%, transparent);
}
.session-item.active {
  background: color-mix(in srgb, var(--bg-muted) 92%, transparent);
  color: var(--text-primary);
  border-left-color: var(--accent-blue);
}
.session-item-top,
.session-item-bottom {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--space-2);
}
.session-title {
  color: color-mix(in srgb, var(--text-primary) 92%, #111 8%);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.session-time {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.session-preview {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.msg-count {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
  margin-left: var(--space-2);
}

@media (max-width: 767px) {
  .channel-header {
    top: 0;
  }
}
</style>
