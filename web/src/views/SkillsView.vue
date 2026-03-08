<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NInput, NButton, NTag, NModal, NUpload, NSpin, useMessage } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import PageLayout from '../components/PageLayout.vue'
import SkeletonCard from '../components/SkeletonCard.vue'
import EmptyState from '../components/EmptyState.vue'
import api from '../api/client'

const message = useMessage()
const loading = ref(true)
const skills = ref<any[]>([])
const selectedSkill = ref<any>(null)
const showDetail = ref(false)
const loadingDetail = ref(false)

// Search
const searchQuery = ref('')
const searchResults = ref<any[]>([])
const searching = ref(false)
const installingSlug = ref('')

// Upload
const showUpload = ref(false)
const uploading = ref(false)

const filteredSkills = computed(() => {
  if (!searchQuery.value.trim()) return skills.value
  const q = searchQuery.value.toLowerCase()
  return skills.value.filter(
    (s: any) => s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)
  )
})

async function loadSkills() {
  try {
    const { data } = await api.get('/skills')
    skills.value = data
  } catch {
    // empty
  } finally {
    loading.value = false
  }
}

async function viewSkill(name: string) {
  showDetail.value = true
  loadingDetail.value = true
  try {
    const { data } = await api.get(`/skills/${encodeURIComponent(name)}`)
    selectedSkill.value = data
  } catch {
    message.error('Failed to load skill details')
    showDetail.value = false
  } finally {
    loadingDetail.value = false
  }
}

async function deleteSkill(name: string) {
  try {
    await api.delete(`/skills/${encodeURIComponent(name)}`)
    message.success(`Deleted ${name}`)
    showDetail.value = false
    selectedSkill.value = null
    await loadSkills()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Failed to delete')
  }
}

async function searchClawhub() {
  const q = searchQuery.value.trim()
  if (!q) return
  searching.value = true
  searchResults.value = []
  try {
    const { data } = await api.get('/skills/search', { params: { q, limit: 10 } })
    searchResults.value = data.results || []
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Search failed')
  } finally {
    searching.value = false
  }
}

async function installSkill(slug: string) {
  installingSlug.value = slug
  try {
    await api.post('/skills/install', { slug })
    message.success(`Installed ${slug}`)
    await loadSkills()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Install failed')
  } finally {
    installingSlug.value = ''
  }
}

async function handleUpload({ file }: { file: UploadFileInfo }) {
  if (!file.file) return
  uploading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.file)
    await api.post('/skills/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    message.success('Skill uploaded')
    showUpload.value = false
    await loadSkills()
  } catch (e: any) {
    message.error(e.response?.data?.detail || 'Upload failed')
  } finally {
    uploading.value = false
  }
}

onMounted(loadSkills)
</script>

<template>
  <PageLayout title="Skills" description="Manage agent skills">
    <!-- Actions bar -->
    <div class="skills-actions">
      <div class="search-row">
        <NInput
          v-model:value="searchQuery"
          placeholder="Filter skills or search clawhub..."
          clearable
          @keydown.enter="searchClawhub"
        />
        <NButton @click="searchClawhub" :loading="searching">Search Clawhub</NButton>
        <NButton @click="showUpload = true">Upload</NButton>
      </div>
    </div>

    <!-- Clawhub search results -->
    <div v-if="searchResults.length > 0" class="clawhub-results">
      <div class="section-label">Clawhub Results</div>
      <div class="result-list">
        <div v-for="(r, i) in searchResults" :key="i" class="result-item">
          <span class="result-text">{{ r.raw }}</span>
          <NButton
            size="small"
            type="primary"
            :loading="installingSlug === r.raw.split(/\s+/)[0]"
            @click="installSkill(r.raw.split(/\s+/)[0])"
          >
            Install
          </NButton>
        </div>
      </div>
    </div>

    <!-- Skills grid -->
    <div v-if="loading" class="skills-grid">
      <SkeletonCard v-for="i in 6" :key="i" :lines="2" />
    </div>

    <template v-else-if="filteredSkills.length === 0">
      <EmptyState icon="◆" title="No skills found" description="Install skills from Clawhub or upload custom skills." />
    </template>

    <div v-else class="skills-grid">
      <div
        v-for="s in filteredSkills"
        :key="s.name"
        class="skill-card"
        @click="viewSkill(s.name)"
      >
        <div class="skill-header">
          <span class="skill-name">{{ s.name }}</span>
          <NTag :type="s.source === 'builtin' ? 'info' : 'success'" size="small">
            {{ s.source }}
          </NTag>
        </div>
        <div class="skill-desc">{{ s.description || 'No description' }}</div>
        <div class="skill-status">
          <NTag :type="s.available ? 'success' : 'warning'" size="small">
            {{ s.available ? 'Available' : 'Unavailable' }}
          </NTag>
        </div>
      </div>
    </div>

    <!-- Skill Detail Modal -->
    <NModal v-model:show="showDetail" preset="card" :title="selectedSkill?.name || 'Skill'" style="max-width: 640px;">
      <NSpin v-if="loadingDetail" />
      <template v-else-if="selectedSkill">
        <div class="detail-meta">
          <NTag :type="selectedSkill.source === 'builtin' ? 'info' : 'success'" size="small">
            {{ selectedSkill.source }}
          </NTag>
          <NTag :type="selectedSkill.available ? 'success' : 'warning'" size="small">
            {{ selectedSkill.available ? 'Available' : 'Unavailable' }}
          </NTag>
        </div>
        <pre class="skill-content">{{ selectedSkill.content }}</pre>
        <div v-if="selectedSkill.source === 'workspace'" class="detail-actions">
          <NButton type="error" @click="deleteSkill(selectedSkill.name)">Delete Skill</NButton>
        </div>
      </template>
    </NModal>

    <!-- Upload Modal -->
    <NModal v-model:show="showUpload" preset="card" title="Upload Skill" style="max-width: 480px;">
      <p class="upload-hint">Upload a SKILL.md file or a .zip archive containing SKILL.md.</p>
      <NUpload
        :custom-request="({ file }: any) => handleUpload({ file })"
        :show-file-list="false"
        accept=".md,.zip"
      >
        <NButton :loading="uploading">Choose File</NButton>
      </NUpload>
    </NModal>
  </PageLayout>
</template>

<style scoped>
.skills-actions {
  margin-bottom: var(--space-4);
}
.search-row {
  display: flex;
  gap: var(--space-3);
  align-items: center;
}
.search-row :deep(.n-input) {
  flex: 1;
}
.clawhub-results {
  margin-bottom: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  padding: var(--space-4);
}
.section-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--space-3);
}
.result-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.result-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  background: var(--bg-muted);
}
.result-text {
  font-size: var(--text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--space-4);
}
.skill-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  padding: var(--space-4);
  cursor: pointer;
  transition: background 150ms, border-color 150ms;
}
.skill-card:hover {
  background: var(--bg-muted);
  border-color: var(--text-muted);
}
.skill-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}
.skill-name {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--text-primary);
}
.skill-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skill-status {
  display: flex;
  gap: var(--space-2);
}
.detail-meta {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.skill-content {
  background: var(--bg-muted);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-size: var(--text-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}
.detail-actions {
  margin-top: var(--space-4);
  display: flex;
  justify-content: flex-end;
}
.upload-hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-3);
}
</style>
