<script setup lang="ts">
import { NButton } from 'naive-ui'
import StatusBadge from './StatusBadge.vue'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const props = defineProps<{
  channel: {
    name: string
    type: string
    configured: boolean
    status: string
  }
}>()

const emit = defineEmits<{
  (e: 'configure'): void
  (e: 'test'): void
}>()

const iconMap: Record<string, string> = {
  telegram: '✈',
  discord: '🎮',
  slack: '#',
  feishu: '🐦',
  dingtalk: '🔔',
  email: '✉',
  whatsapp: '📱',
  qq: '🐧',
  matrix: '▣',
  wechat: '💬',
  mochat: '🤖',
}
</script>

<template>
  <div class="channel-card" :class="{ unconfigured: !channel.configured }">
    <div class="card-header">
      <span class="channel-icon" aria-hidden="true">{{ iconMap[channel.type] || '◉' }}</span>
      <div class="channel-info">
        <span class="channel-name">{{ channel.name }}</span>
      </div>
      <StatusBadge :status="channel.configured ? 'online' : 'offline'" />
    </div>

    <div class="card-body">
      <span class="config-status">
        {{ channel.configured ? t('common.configured') : t('common.notConfigured') }}
      </span>
    </div>

    <div class="card-actions">
      <NButton size="small" quaternary @click="emit('configure')">{{ t('common.configure') }}</NButton>
      <NButton v-if="channel.configured" size="small" quaternary @click="emit('test')">{{ t('common.test') }}</NButton>
    </div>
  </div>
</template>

<style scoped>
.channel-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: border-color 200ms var(--ease-default), box-shadow 200ms var(--ease-default);
}
.channel-card:hover {
  border-color: var(--text-muted);
  box-shadow: var(--shadow-sm);
}
.channel-card.unconfigured {
  border-style: dashed;
  opacity: 0.7;
}
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.channel-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  flex-shrink: 0;
}
.channel-info {
  flex: 1;
}
.channel-name {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
  text-transform: capitalize;
}
.card-body {
  margin-bottom: var(--space-4);
}
.config-status {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
.card-actions {
  display: flex;
  gap: var(--space-2);
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
</style>
