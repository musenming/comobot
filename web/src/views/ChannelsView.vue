<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ChannelCard from '../components/ChannelCard.vue'
import ChannelConfigDrawer from '../components/ChannelConfigDrawer.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import { useWebSocket } from '../composables/useWebSocket'
import api from '../api/client'

const message = useMessage()
const loading = ref(true)
const channels = ref<any[]>([])
const drawerOpen = ref(false)
const selectedChannel = ref<string | null>(null)
const selectedFields = ref<any[]>([])

async function loadChannels() {
  try {
    const { data } = await api.get('/channels')
    channels.value = data
  } catch {
    message.error('Failed to load channels')
  } finally {
    loading.value = false
  }
}

function openConfig(ch: any) {
  selectedChannel.value = ch.type
  selectedFields.value = ch.fields || []
  drawerOpen.value = true
}

async function testChannel(ch: any) {
  try {
    const { data } = await api.post(`/channels/${ch.type}/test`)
    message.success(data.message || 'Test passed')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Test failed')
  }
}

onMounted(loadChannels)

// Live channel status updates via WebSocket
const { data: wsStatus } = useWebSocket('/ws/status')
watch(wsStatus, (s) => {
  if (s?.type === 'status' && s.channels) {
    for (const ch of channels.value) {
      if (s.channels[ch.type]) {
        ch.status = s.channels[ch.type]
      }
    }
  }
})
</script>

<template>
  <PageLayout title="Channels" description="Manage your communication channels">
    <div v-if="loading" class="channel-grid">
      <SkeletonCard v-for="i in 6" :key="i" height="180px" />
    </div>
    <div v-else class="channel-grid">
      <ChannelCard
        v-for="ch in channels"
        :key="ch.type"
        :channel="ch"
        @configure="openConfig(ch)"
        @test="testChannel(ch)"
      />
    </div>

    <ChannelConfigDrawer
      v-model:show="drawerOpen"
      :channel-type="selectedChannel"
      :fields="selectedFields"
      @saved="loadChannels"
    />
  </PageLayout>
</template>

<style scoped>
.channel-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}
@media (max-width: 1023px) {
  .channel-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 767px) {
  .channel-grid { grid-template-columns: 1fr; }
}
</style>
