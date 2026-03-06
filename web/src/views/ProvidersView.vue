<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ProviderCard from '../components/ProviderCard.vue'
import ProviderDrawer from '../components/ProviderDrawer.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const message = useMessage()
const loading = ref(true)
const providers = ref<any[]>([])
const drawerOpen = ref(false)
const editProvider = ref<string | null>(null)

async function loadProviders() {
  try {
    const { data } = await api.get('/providers')
    providers.value = data
  } catch {
    // may fail if no providers
  } finally {
    loading.value = false
  }
}

function openAdd() {
  editProvider.value = null
  drawerOpen.value = true
}

function openEdit(p: any) {
  editProvider.value = p.provider
  drawerOpen.value = true
}

async function testProvider(p: any) {
  try {
    const { data } = await api.post(`/providers/${p.provider}/test`)
    message.success(`Test passed - ${data.key_prefix}`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Test failed')
  }
}

async function removeProvider(p: any) {
  try {
    await api.delete(`/providers/${p.provider}/api_key`)
    message.success('Provider removed')
    await loadProviders()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to remove')
  }
}

onMounted(loadProviders)
</script>

<template>
  <PageLayout title="Providers" description="Configure your AI model providers">
    <template #actions>
      <NButton type="primary" @click="openAdd">+ Add Provider</NButton>
    </template>

    <div v-if="loading" class="provider-grid">
      <SkeletonCard v-for="i in 3" :key="i" height="160px" />
    </div>
    <template v-else-if="providers.length === 0">
      <EmptyState icon="◆" title="No providers configured" description="Add your first LLM provider to get started.">
        <NButton type="primary" @click="openAdd">+ Add Provider</NButton>
      </EmptyState>
    </template>
    <div v-else class="provider-grid">
      <ProviderCard
        v-for="p in providers"
        :key="p.provider"
        :provider="p"
        @edit="openEdit(p)"
        @test="testProvider(p)"
        @remove="removeProvider(p)"
      />
    </div>

    <ProviderDrawer
      v-model:show="drawerOpen"
      :edit-provider="editProvider"
      @saved="loadProviders"
    />
  </PageLayout>
</template>

<style scoped>
.provider-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}
@media (max-width: 1023px) {
  .provider-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 767px) {
  .provider-grid { grid-template-columns: 1fr; }
}
</style>
