<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NCard, NFormItem, NInput, NSelect, NSwitch, NTag, useMessage } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import ProviderCard from '../components/ProviderCard.vue'
import ProviderDrawer from '../components/ProviderDrawer.vue'
import ASRDrawer from '../components/ASRDrawer.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import { useI18n } from '../composables/useI18n'
import api, { restartGateway } from '../api/client'

const { t } = useI18n()

const message = useMessage()
const loading = ref(true)
const providers = ref<any[]>([])
const drawerOpen = ref(false)
const editProvider = ref<string | null>(null)

// Defaults (moved from Settings)
const defaultsForm = ref({ model: '', provider: 'auto' })
const savingDefaults = ref(false)
const providerOptions = ref<{ label: string; value: string }[]>([{ label: 'Auto', value: 'auto' }])

// ASR state
const asrProviders = ref<any[]>([])
const asrEnabled = ref(false)
const asrActiveProvider = ref('')
const asrDrawerOpen = ref(false)
const asrEditProvider = ref<string | null>(null)

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

async function loadASR() {
  try {
    const { data } = await api.get('/asr')
    asrProviders.value = data.providers || []
    asrEnabled.value = data.enabled || false
    asrActiveProvider.value = data.active_provider || ''
  } catch {
    // ignore
  }
}

async function saveDefaults() {
  savingDefaults.value = true
  try {
    await api.put('/settings/defaults', defaultsForm.value)
    message.success(t('providers.defaultsSaved'))
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('providers.failedSaveDefaults'))
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
    message.success(`${t('providers.testPassed')} ${data.key_prefix}`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('providers.testFailed'))
  }
}

async function removeProvider(p: any) {
  try {
    await api.delete(`/providers/${p.provider}/api_key`)
    message.success(t('providers.removed'))
    await loadProviders()
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('providers.failedRemove'))
  }
}

// ASR actions
function openASRAdd() {
  asrEditProvider.value = null
  asrDrawerOpen.value = true
}

function openASREdit(p: any) {
  asrEditProvider.value = p.provider
  asrDrawerOpen.value = true
}

async function testASRProvider(p: any) {
  try {
    const { data } = await api.post(`/asr/${p.provider}/test`)
    message.success(`${t('asr.testPassed')} ${data.key_prefix}`)
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.testFailed'))
  }
}

async function removeASRProvider(p: any) {
  try {
    await api.delete(`/asr/${p.provider}`)
    message.success(t('asr.removed'))
    await loadASR()
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.failedRemove'))
  }
}

async function setASRActive(provider: string) {
  try {
    await api.put('/asr/active', { provider, enabled: true })
    asrActiveProvider.value = provider
    asrEnabled.value = true
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.failedSave'))
  }
}

async function toggleASREnabled(enabled: boolean) {
  try {
    await api.put('/asr/active', { provider: asrActiveProvider.value, enabled })
    asrEnabled.value = enabled
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('asr.failedSave'))
  }
}

const asrNameMap: Record<string, string> = {
  groq: 'Groq',
  openai: 'OpenAI',
  azure: 'Azure',
  deepseek: 'DeepSeek',
  siliconflow: 'SiliconFlow',
  custom: 'Custom',
}

onMounted(async () => {
  await Promise.all([loadProviders(), loadDefaults(), loadASR()])
})
</script>

<template>
  <PageLayout :title="t('providers.title')" :description="t('providers.subtitle')">
    <template #actions>
      <NButton type="primary" @click="openAdd">{{ t('providers.addProvider') }}</NButton>
    </template>

    <!-- Default Model & Provider selector (above provider cards) -->
    <NCard class="defaults-card" :bordered="true" size="small">
      <div class="defaults-row">
        <NFormItem :label="t('providers.defaultModel')" :show-feedback="false" class="defaults-field">
          <NInput
            v-model:value="defaultsForm.model"
            :placeholder="t('providers.defaultModelPlaceholder')"
            size="small"
          />
        </NFormItem>
        <NFormItem :label="t('providers.defaultProvider')" :show-feedback="false" class="defaults-field">
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
          {{ t('common.save') }}
        </NButton>
      </div>
    </NCard>

    <div v-if="loading" class="provider-grid">
      <SkeletonCard v-for="i in 3" :key="i" height="160px" />
    </div>
    <template v-else-if="providers.length === 0">
      <EmptyState icon="&#9670;" :title="t('providers.noProviders')" :description="t('providers.noProvidersDesc')">
        <NButton type="primary" @click="openAdd">{{ t('providers.addProvider') }}</NButton>
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

    <!-- ASR Provider Section -->
    <div class="section-header">
      <div class="section-title-row">
        <h3 class="section-title">{{ t('asr.title') }}</h3>
        <NSwitch
          :value="asrEnabled"
          :disabled="!asrActiveProvider"
          @update:value="toggleASREnabled"
        />
      </div>
      <p class="section-desc">{{ t('asr.subtitle') }}</p>
    </div>

    <div v-if="asrProviders.length === 0" class="asr-empty">
      <EmptyState icon="&#9834;" :title="t('asr.noProviders')" :description="t('asr.noProvidersDesc')">
        <NButton type="primary" @click="openASRAdd">{{ t('asr.addProvider') }}</NButton>
      </EmptyState>
    </div>
    <template v-else>
      <div class="provider-grid">
        <div
          v-for="p in asrProviders"
          :key="p.provider"
          class="provider-card"
          :class="{ 'card-active': p.active }"
        >
          <div class="card-header">
            <div class="provider-icon" aria-hidden="true">&#9834;</div>
            <div class="provider-info">
              <span class="provider-name">{{ asrNameMap[p.provider] || p.provider }}</span>
              <span class="provider-meta">{{ p.model || 'whisper' }}</span>
            </div>
            <NTag v-if="p.active" size="small" type="success">{{ t('asr.active') }}</NTag>
          </div>
          <div class="card-actions">
            <NButton v-if="!p.active" size="small" quaternary @click="setASRActive(p.provider)">{{ t('asr.setActive') }}</NButton>
            <NButton size="small" quaternary @click="openASREdit(p)">{{ t('common.edit') }}</NButton>
            <NButton size="small" quaternary @click="testASRProvider(p)">{{ t('common.test') }}</NButton>
            <NButton size="small" quaternary type="error" @click="removeASRProvider(p)">{{ t('providers.remove') }}</NButton>
          </div>
        </div>
      </div>
      <div style="margin-top: var(--space-3)">
        <NButton @click="openASRAdd">{{ t('asr.addProvider') }}</NButton>
      </div>
    </template>

    <ASRDrawer
      v-model:show="asrDrawerOpen"
      :edit-provider="asrEditProvider"
      @saved="loadASR"
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
.section-header {
  margin-top: var(--space-8);
  margin-bottom: var(--space-4);
}
.section-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.section-title {
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.section-desc {
  font-size: var(--text-sm);
  color: var(--text-muted);
  margin: var(--space-1) 0 0;
}
.provider-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  transition: border-color 200ms var(--ease-default), box-shadow 200ms var(--ease-default);
}
.provider-card:hover {
  border-color: var(--text-muted);
  box-shadow: var(--shadow-sm);
}
.provider-card.card-active {
  border-color: var(--accent-green, #22c55e);
}
.card-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}
.provider-icon {
  font-size: 24px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-muted);
  border-radius: var(--radius-md);
}
.provider-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.provider-name {
  font-size: var(--text-md);
  font-weight: 500;
  color: var(--text-primary);
}
.provider-meta {
  font-size: var(--text-xs);
  color: var(--text-muted);
}
.card-actions {
  display: flex;
  gap: var(--space-2);
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
@media (max-width: 1023px) {
  .provider-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 767px) {
  .provider-grid { grid-template-columns: 1fr; }
  .defaults-row { flex-direction: column; }
}
</style>
