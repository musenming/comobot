<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { NInput, NTag } from 'naive-ui'
import api from '../api/client'
import { useI18n } from '../composables/useI18n'

const { t } = useI18n()

const emit = defineEmits<{ select: [id: string] }>()

const items = ref<any[]>([])
const search = ref('')
const loading = ref(true)

const filtered = computed(() =>
  items.value.filter(
    (i) => !search.value || i.title.includes(search.value) || JSON.stringify(i.tags).includes(search.value),
  ),
)

async function load() {
  try {
    const { data } = await api.get('/knowhow')
    items.value = data
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

onMounted(load)

defineExpose({ reload: load })
</script>

<template>
  <div class="knowhow-sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">{{ t('knowhow.title') }}</span>
      <n-input
        v-model:value="search"
        size="small"
        :placeholder="t('knowhow.search')"
        clearable
        style="max-width: 140px"
      />
    </div>
    <div v-if="loading" class="sidebar-loading">{{ t('common.loading') }}</div>
    <div v-else-if="filtered.length === 0" class="sidebar-empty">
      {{ search ? t('knowhow.noMatches') : t('knowhow.noKnowhowYet') }}
    </div>
    <div v-else class="knowhow-list">
      <div
        v-for="item in filtered"
        :key="item.id"
        class="knowhow-item"
        @click="emit('select', item.id)"
      >
        <div class="kh-title">{{ item.title }}</div>
        <div class="kh-tags">
          <n-tag
            v-for="tag in (Array.isArray(item.tags) ? item.tags : [])"
            :key="tag"
            size="tiny"
            :bordered="false"
          >
            {{ tag }}
          </n-tag>
          <span v-if="item.suggest_upgrade" class="upgrade-hint" title="Consider upgrading to Skill">*</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowhow-sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--border);
}
.sidebar-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}
.sidebar-loading, .sidebar-empty {
  padding: var(--space-4);
  color: var(--text-muted);
  font-size: var(--text-xs);
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
.kh-title {
  font-size: var(--text-sm);
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kh-tags {
  display: flex;
  gap: 4px;
  margin-top: 2px;
  flex-wrap: wrap;
  align-items: center;
}
.upgrade-hint {
  color: var(--accent-yellow, #f59e0b);
  font-weight: bold;
  font-size: var(--text-xs);
}
</style>
