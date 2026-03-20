<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NTag, NDynamicTags, NInput, NSpace, NPopconfirm } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import MarkdownRenderer from '../components/MarkdownRenderer.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const route = useRoute()
const router = useRouter()

// List state
const items = ref<any[]>([])
const search = ref('')
const listLoading = ref(true)
const selectedId = ref<string | null>(null)

// Detail state
const item = ref<any>(null)
const detailLoading = ref(false)
const editing = ref(false)
const editTitle = ref('')
const editTags = ref<string[]>([])

const filtered = computed(() =>
  items.value.filter(
    (i) => !search.value || i.title.includes(search.value) || JSON.stringify(i.tags).includes(search.value),
  ),
)

async function loadList() {
  try {
    const { data } = await api.get('/knowhow')
    items.value = data
  } catch {
    items.value = []
  } finally {
    listLoading.value = false
  }
}

async function loadDetail(id: string) {
  selectedId.value = id
  detailLoading.value = true
  editing.value = false
  try {
    const { data } = await api.get(`/knowhow/${id}`)
    item.value = data
    editTitle.value = data.title
    editTags.value = Array.isArray(data.tags) ? [...data.tags] : []
  } catch {
    item.value = null
  } finally {
    detailLoading.value = false
  }
}

function selectItem(id: string) {
  router.replace(`/knowhow/${id}`)
  loadDetail(id)
}

async function save() {
  if (!item.value) return
  try {
    const { data } = await api.put(`/knowhow/${item.value.id}`, {
      title: editTitle.value,
      tags: editTags.value,
    })
    item.value = data
    editing.value = false
    // Update list item title
    const listItem = items.value.find((i: any) => i.id === data.id)
    if (listItem) {
      listItem.title = data.title
      listItem.tags = data.tags
    }
  } catch {
    // error
  }
}

async function archive() {
  if (!item.value) return
  await api.put(`/knowhow/${item.value.id}`, { status: 'archived' })
  item.value = null
  selectedId.value = null
  router.replace('/knowhow')
  await loadList()
}

async function remove() {
  if (!item.value) return
  await api.delete(`/knowhow/${item.value.id}`)
  item.value = null
  selectedId.value = null
  router.replace('/knowhow')
  await loadList()
}

// Watch route param changes
watch(() => route.params.id, (newId) => {
  if (newId && typeof newId === 'string') {
    loadDetail(newId)
  }
})

onMounted(async () => {
  await loadList()
  const id = route.params.id as string
  if (id) {
    await loadDetail(id)
  }
})
</script>

<template>
  <PageLayout :title="t('knowhow.title')" :description="t('knowhow.subtitle')">
    <div class="knowhow-layout">
      <!-- Left panel: search + list -->
      <div class="knowhow-sidebar">
        <div class="sidebar-header">
          <n-input
            v-model:value="search"
            size="small"
            :placeholder="t('knowhow.searchPlaceholder')"
            clearable
          />
        </div>
        <div v-if="listLoading" class="sidebar-loading">{{ t('common.loading') }}</div>
        <div v-else-if="filtered.length === 0" class="sidebar-empty">
          {{ search ? t('knowhow.noMatches') : t('knowhow.noKnowhowYet') }}
        </div>
        <div v-else class="knowhow-list">
          <div
            v-for="kh in filtered"
            :key="kh.id"
            class="knowhow-item"
            :class="{ active: kh.id === selectedId }"
            @click="selectItem(kh.id)"
          >
            <div class="kh-title">{{ kh.title }}</div>
            <div class="kh-meta-row">
              <span class="kh-time">{{ kh.updated_at || kh.created_at }}</span>
              <span v-if="kh.suggest_upgrade" class="upgrade-hint" title="Consider upgrading to Skill">*</span>
            </div>
            <div class="kh-tags">
              <n-tag
                v-for="tag in (Array.isArray(kh.tags) ? kh.tags : [])"
                :key="tag"
                size="tiny"
                :bordered="false"
              >
                {{ tag }}
              </n-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- Right panel: detail -->
      <div class="knowhow-detail">
        <div v-if="detailLoading" style="padding: 20px; color: var(--text-muted)">{{ t('common.loading') }}</div>
        <template v-else-if="item">
          <!-- Detail header -->
          <div class="detail-header">
            <div v-if="editing" class="edit-header">
              <n-input v-model:value="editTitle" size="small" style="flex: 1" />
              <n-button size="small" type="primary" @click="save">{{ t('common.save') }}</n-button>
              <n-button size="small" @click="editing = false">{{ t('common.cancel') }}</n-button>
            </div>
            <div v-else class="view-header">
              <h3 class="detail-title">{{ item.title }}</h3>
              <n-space>
                <n-button size="small" quaternary @click="editing = true">{{ t('common.edit') }}</n-button>
                <n-button size="small" quaternary @click="archive">{{ t('knowhow.archive') }}</n-button>
                <n-popconfirm @positive-click="remove">
                  <template #trigger>
                    <n-button size="small" quaternary type="error">{{ t('common.delete') }}</n-button>
                  </template>
                  {{ t('knowhow.permanentlyDelete') }}
                </n-popconfirm>
              </n-space>
            </div>
          </div>

          <!-- Detail meta -->
          <div class="kh-detail-meta">
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.id') }}</span>
              <code>{{ item.id }}</code>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.statusLabel') }}</span>
              <n-tag :type="item.status === 'active' ? 'success' : 'default'" size="small">
                {{ item.status }}
              </n-tag>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.source') }}</span>
              <code>{{ item.source_session || '-' }}</code>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.usage') }}</span>
              <span>{{ item.usage_count || 0 }} {{ t('knowhow.times') }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.tags') }}</span>
              <div v-if="editing">
                <n-dynamic-tags v-model:value="editTags" />
              </div>
              <div v-else class="tag-list">
                <n-tag v-for="tag in (Array.isArray(item.tags) ? item.tags : [])" :key="tag" size="small">
                  {{ tag }}
                </n-tag>
              </div>
            </div>
            <div class="meta-row">
              <span class="meta-label">{{ t('knowhow.created') }}</span>
              <span>{{ item.created_at }}</span>
            </div>
          </div>

          <!-- Detail content -->
          <div v-if="item.content" class="kh-content">
            <MarkdownRenderer :content="item.content" />
          </div>
        </template>
        <EmptyState v-else :title="t('knowhow.selectKnowhow')" :description="t('knowhow.selectKnowhowDesc')" />
      </div>
    </div>
  </PageLayout>
</template>

<style scoped>
.knowhow-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: var(--space-4);
  min-height: 60vh;
}
.knowhow-sidebar {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: 80vh;
  overflow: hidden;
}
.sidebar-header {
  padding: var(--space-3);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sidebar-loading, .sidebar-empty {
  padding: var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-sm);
  text-align: center;
}
.knowhow-list {
  overflow-y: auto;
  flex: 1;
}
.knowhow-item {
  padding: var(--space-2) var(--space-3);
  cursor: pointer;
  border-bottom: 1px solid var(--border);
}
.knowhow-item:hover {
  background: var(--bg-muted);
}
.knowhow-item.active {
  background: var(--bg-muted);
  border-left: 2px solid var(--text-primary);
}
.kh-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kh-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 2px;
}
.kh-time {
  font-size: var(--text-xs);
  color: var(--text-muted);
}
.upgrade-hint {
  color: var(--accent-yellow, #f59e0b);
  font-weight: bold;
  font-size: var(--text-xs);
}
.kh-tags {
  display: flex;
  gap: 4px;
  margin-top: 2px;
  flex-wrap: wrap;
}
.knowhow-detail {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  max-height: 80vh;
  overflow-y: auto;
  padding: var(--space-6);
}
.detail-header {
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--border);
}
.edit-header {
  display: flex;
  gap: 8px;
  align-items: center;
}
.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.detail-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--text-primary);
}
.kh-detail-meta {
  margin-bottom: var(--space-6);
}
.meta-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  padding: var(--space-1) 0;
  font-size: var(--text-sm);
}
.meta-label {
  color: var(--text-muted);
  min-width: 80px;
  flex-shrink: 0;
}
.tag-list {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.kh-content {
  border-top: 1px solid var(--border);
  padding-top: var(--space-4);
}

@media (max-width: 767px) {
  .knowhow-layout {
    grid-template-columns: 1fr;
  }
  .knowhow-sidebar {
    max-height: 40vh;
  }
}
</style>
