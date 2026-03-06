<script setup lang="ts">
import { NDataTable } from 'naive-ui'
import SkeletonCard from './SkeletonCard.vue'
import EmptyState from './EmptyState.vue'

defineProps<{
  columns: any[]
  data: any[]
  loading?: boolean
  emptyIcon?: string
  emptyTitle?: string
  emptyDescription?: string
}>()
</script>

<template>
  <div class="data-table-wrapper">
    <div v-if="loading" class="table-skeleton">
      <SkeletonCard v-for="i in 5" :key="i" :lines="1" />
    </div>
    <template v-else-if="data.length === 0">
      <EmptyState
        :icon="emptyIcon || '📭'"
        :title="emptyTitle || 'No data'"
        :description="emptyDescription"
      >
        <slot name="empty" />
      </EmptyState>
    </template>
    <NDataTable v-else :columns="columns" :data="data" :bordered="false" />
  </div>
</template>

<style scoped>
.table-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
</style>
