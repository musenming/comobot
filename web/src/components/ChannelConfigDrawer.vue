<script setup lang="ts">
import { ref, watch } from 'vue'
import { NDrawer, NDrawerContent, NForm, NFormItem, NInput, NSelect, NButton, NSpace, NDynamicTags, NSpin, useMessage } from 'naive-ui'
import SecretInput from './SecretInput.vue'
import api, { restartGateway } from '../api/client'
import { useI18n } from '../composables/useI18n'

const props = defineProps<{
  show: boolean
  channelType: string | null
  fields: any[]
}>()

const emit = defineEmits<{
  (e: 'update:show', val: boolean): void
  (e: 'saved'): void
}>()

const { t } = useI18n()
const message = useMessage()
const form = ref<Record<string, any>>({})
const testing = ref(false)
const saving = ref(false)

// WeChat QR login state
const wechatQrUrl = ref('')
const wechatToken = ref('')
const wechatUin = ref('')
const wechatLoading = ref(false)
const wechatStatus = ref<'idle' | 'qr' | 'scanned' | 'confirmed' | 'expired' | 'error'>('idle')
const wechatMessage = ref('')

async function fetchWechatQr() {
  wechatLoading.value = true
  wechatStatus.value = 'idle'
  wechatMessage.value = ''
  try {
    const { data } = await api.post('/channels/wechat/qr')
    if (data.success) {
      wechatQrUrl.value = data.image_url
      wechatToken.value = data.qrcode_token
      wechatUin.value = data.uin
      wechatStatus.value = 'qr'
    } else {
      wechatStatus.value = 'error'
      wechatMessage.value = data.message || t('channels.wechatQrFailed')
    }
  } catch {
    wechatStatus.value = 'error'
    wechatMessage.value = t('channels.wechatQrFailed')
  } finally {
    wechatLoading.value = false
  }
}

async function pollWechatStatus() {
  if (!wechatToken.value || !wechatUin.value) return
  wechatLoading.value = true
  try {
    const { data } = await api.post('/channels/wechat/qr/poll', {
      qrcode_token: wechatToken.value,
      uin: wechatUin.value,
    })
    if (data.status === 'confirmed') {
      wechatStatus.value = 'confirmed'
      wechatMessage.value = t('channels.wechatLoginSuccess')
      // Reload channels list
      emit('saved')
    } else if (data.status === 'scanned') {
      wechatStatus.value = 'scanned'
      wechatMessage.value = t('channels.wechatScanned')
    } else if (data.status === 'expired') {
      wechatStatus.value = 'expired'
      wechatMessage.value = t('channels.wechatExpired')
    } else {
      wechatStatus.value = 'qr'
      wechatMessage.value = t('channels.wechatNotScanned')
    }
  } catch {
    wechatStatus.value = 'error'
    wechatMessage.value = t('channels.wechatPollFailed')
  } finally {
    wechatLoading.value = false
  }
}

watch(() => [props.show, props.channelType], async () => {
  if (props.show && props.channelType) {
    try {
      const { data } = await api.get(`/channels/${props.channelType}/config`)
      form.value = data.config || {}
    } catch {
      form.value = {}
    }
  }
})

async function save() {
  if (!props.channelType) return
  saving.value = true
  try {
    await api.put(`/channels/${props.channelType}/config`, { config: form.value })
    message.success(t('channels.saveRestart'))
    emit('saved')
    emit('update:show', false)
    restartGateway()
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('channels.failedSave'))
  } finally {
    saving.value = false
  }
}

async function test() {
  if (!props.channelType) return
  testing.value = true
  try {
    const { data } = await api.post(`/channels/${props.channelType}/test`)
    message.success(data.message || t('channels.testPassed'))
  } catch (e: any) {
    message.error(e.response?.data?.detail || t('channels.testFailed'))
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <NDrawer :show="show" :width="480" placement="right" @update:show="(v: boolean) => emit('update:show', v)">
    <NDrawerContent :title="`Configure ${channelType}`">
      <!-- WeChat: QR code login flow -->
      <template v-if="channelType === 'wechat'">
        <div class="wechat-qr-section">
          <template v-if="wechatStatus === 'idle' && !wechatLoading">
            <NButton type="primary" size="large" @click="fetchWechatQr">
              {{ t('channels.wechatGenerateQr') }}
            </NButton>
          </template>

          <div v-else-if="wechatStatus === 'idle' && wechatLoading" class="qr-loading">
            <NSpin size="large" />
          </div>

          <template v-else-if="wechatStatus === 'qr' || wechatStatus === 'scanned'">
            <div class="qr-image-wrapper">
              <img :src="wechatQrUrl" alt="WeChat QR" class="qr-image" />
            </div>
            <div class="qr-actions">
              <NButton type="primary" :loading="wechatLoading" @click="pollWechatStatus">
                {{ t('channels.wechatCheckScan') }}
              </NButton>
              <NButton quaternary @click="fetchWechatQr">
                {{ t('channels.wechatRefreshQr') }}
              </NButton>
            </div>
            <div v-if="wechatMessage" class="qr-hint">{{ wechatMessage }}</div>
          </template>

          <div v-else-if="wechatStatus === 'confirmed'" class="qr-result success">
            ✅ {{ wechatMessage }}
          </div>

          <div v-else-if="wechatStatus === 'expired'" class="qr-result expired">
            <span>{{ wechatMessage }}</span>
            <NButton size="small" @click="fetchWechatQr">{{ t('channels.wechatRefreshQr') }}</NButton>
          </div>

          <div v-else-if="wechatStatus === 'error'" class="qr-result error">
            <span>{{ wechatMessage }}</span>
            <NButton size="small" @click="fetchWechatQr">{{ t('channels.wechatRetry') }}</NButton>
          </div>
        </div>
      </template>

      <!-- Other channels: standard config form -->
      <NForm v-else label-placement="top">
        <NFormItem v-for="field in fields" :key="field.key" :label="field.label">
          <SecretInput
            v-if="field.type === 'secret'"
            :value="form[field.key] || ''"
            :placeholder="field.label"
            @update:value="(v: string) => form[field.key] = v"
          />
          <NSelect
            v-else-if="field.type === 'select'"
            :value="form[field.key] || field.default"
            :options="(field.options || []).map((o: string) => ({ label: o, value: o }))"
            @update:value="(v: string) => form[field.key] = v"
          />
          <NDynamicTags
            v-else-if="field.type === 'tags'"
            :value="Array.isArray(form[field.key]) ? form[field.key] : []"
            @update:value="(v: string[]) => form[field.key] = v"
          />
          <NInput
            v-else
            :value="form[field.key] || ''"
            :placeholder="field.label"
            @update:value="(v: string) => form[field.key] = v"
          />
        </NFormItem>
      </NForm>

      <template #footer>
        <NSpace v-if="channelType !== 'wechat'" justify="space-between" style="width: 100%">
          <NButton :loading="testing" @click="test">{{ t('channels.testConnection') }}</NButton>
          <NSpace>
            <NButton @click="emit('update:show', false)">{{ t('common.cancel') }}</NButton>
            <NButton type="primary" :loading="saving" @click="save">{{ t('channels.saveApply') }}</NButton>
          </NSpace>
        </NSpace>
        <NSpace v-else justify="end" style="width: 100%">
          <NButton @click="emit('update:show', false)">{{ t('common.cancel') }}</NButton>
        </NSpace>
      </template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>
.wechat-qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-6) 0;
}
.qr-loading {
  padding: var(--space-8) 0;
}
.qr-image-wrapper {
  background: #fff;
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  box-shadow: var(--shadow-sm);
}
.qr-image {
  width: 240px;
  height: 240px;
  display: block;
}
.qr-actions {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.qr-result {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: var(--text-sm);
  width: 100%;
}
.qr-result.success {
  background: color-mix(in srgb, var(--accent-green) 10%, transparent);
  color: var(--accent-green);
  border: 1px solid color-mix(in srgb, var(--accent-green) 30%, transparent);
}
.qr-result.expired {
  background: color-mix(in srgb, var(--accent-yellow) 10%, transparent);
  color: var(--accent-yellow);
  border: 1px solid color-mix(in srgb, var(--accent-yellow) 30%, transparent);
}
.qr-result.error {
  background: color-mix(in srgb, var(--accent-red) 10%, transparent);
  color: var(--accent-red);
  border: 1px solid color-mix(in srgb, var(--accent-red) 30%, transparent);
}
.qr-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
