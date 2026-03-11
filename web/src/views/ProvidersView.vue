<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NCard, NFormItem, NInput, NSelect, useMessage } from 'naive-ui'
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

// Defaults (moved from Settings)
const defaultsForm = ref({ model: '', provider: 'auto' })
const savingDefaults = ref(false)
const providerOptions = ref<{ label: string; value: string }[]>([{ label: 'Auto', value: 'auto' }])

async function loadProviders() {
  try {
    const { data } = await api.get('/providers')
    providers.value = data

    // Build provider options for the defaults selector
    const opts = [{ label: 'Auto', value: 'auto' }]
    for (const p of data) {
      opts.push({ label: p.provider, value: p.provider })
    }
    providerOptions.value = opts
  } catch {
    // may fail if no providers
  } finally {
    loading.value = false
  }
}

async function loadDefaults() {
  try {
    const { data } = await api.get('/settings/defaults')
    if (data) {
      defaultsForm.value.model = data.model || ''
      defaultsForm.value.provider = data.provider || 'auto'
    }
  } catch {
    // ignore
  }
}

async function saveDefaults() {
  savingDefaults.value = true
  try {
    await api.put('/settings/defaults', defaultsForm.value)
    message.success('Defaults saved')
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to save defaults')
  } finally {
    savingDefaults.value = false
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

onMounted(async () => {
  await Promise.all([loadProviders(), loadDefaults()])
})
</script>

<template>
  <PageLayout title="Providers" description="Configure your AI model providers">
    <template #actions>
      <NButton type="primary" @click="openAdd">+ Add Provider</NButton>
    </template>

    <!-- Default Model & Provider selector (above provider cards) -->
    <NCard class="defaults-card" :bordered="true" size="small">
      <div class="defaults-row">
        <NFormItem label="Default Model" :show-feedback="false" class="defaults-field">
          <NInput
            v-model:value="defaultsForm.model"
            placeholder="e.g. anthropic/claude-opus-4-5"
            size="small"
          />
        </NFormItem>
        <NFormItem label="Default Provider" :show-feedback="false" class="defaults-field">
          <NSelect
            v-model:value="defaultsForm.provider"
            :options="providerOptions"
            size="small"
          />
        </NFormItem>
        <NButton
          type="primary"
          size="small"
          :loading="savingDefaults"
          class="defaults-save"
          @click="saveDefaults"
        >
          Save
        </NButton>
      </div>
    </NCard>

    <div v-if="loading" class="provider-grid">
      <SkeletonCard v-for="i in 3" :key="i" height="160px" />
    </div>
    <template v-else-if="providers.length === 0">
      <EmptyState icon="&#9670;" title="No providers configured" description="Add your first LLM provider to get started.">
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
.defaults-card {
  margin-bottom: var(--space-4);
}
.defaults-row {
  display: flex;
  gap: var(--space-4);
  align-items: flex-end;
  flex-wrap: wrap;
}
.defaults-field {
  flex: 1;
  min-width: 200px;
}
.defaults-save {
  flex-shrink: 0;
  margin-bottom: 2px;
}
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
  .defaults-row { flex-direction: column; }
}
</style>
