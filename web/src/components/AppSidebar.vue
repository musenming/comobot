<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NTooltip } from 'naive-ui'
import { useBreakpoints } from '@vueuse/core'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import StatusBadge from './StatusBadge.vue'

const props = defineProps<{
  agentStatus?: 'online' | 'offline' | 'error' | 'paused'
}>()

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const themeStore = useThemeStore()

const breakpoints = useBreakpoints({ md: 768, lg: 1024 })
const isTablet = breakpoints.between('md', 'lg')
const isMobile = breakpoints.smaller('md')

const collapsed = ref(false)
const mobileOpen = ref(false)

const sidebarCollapsed = computed(() => {
  if (isMobile.value) return true
  if (isTablet.value) return true
  return collapsed.value
})

const menuItems = [
  { key: '/chat', label: 'Chat', icon: '◬' },
  { key: '/workflows', label: 'Creflow', icon: '⚡' },
  { key: '/knowhow', label: 'Knowhow', icon: '◎' },
  { key: '/skills', label: 'Skills', icon: '◇' },
  { key: '/cron', label: 'Cron Jobs', icon: '◷' },

  { key: '/memory', label: 'Memory', icon: '◐' },

  { key: 'divider' },
  { key: '/', label: 'Dashboard', icon: '◈' },
  { key: '/channels', label: 'Channels', icon: '◉' },
  { key: '/providers', label: 'Providers', icon: '◆' },
  { key: '/logs', label: 'Logs', icon: '▤' },
  { key: '/settings', label: 'Settings', icon: '⚙' },
]

function isActive(key: string) {
  if (key === '/') return route.path === '/'
  return route.path.startsWith(key)
}

function navigate(key: string) {
  router.push(key)
  mobileOpen.value = false
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

function toggleCollapse() {
  if (isMobile.value) {
    mobileOpen.value = !mobileOpen.value
  } else {
    collapsed.value = !collapsed.value
  }
}
</script>

<template>
  <!-- Mobile hamburger -->
  <button
    v-if="isMobile"
    class="hamburger"
    aria-label="Toggle menu"
    @click="mobileOpen = true"
  >
    ☰
  </button>

  <!-- Mobile overlay -->
  <Transition name="overlay-fade">
    <div v-if="isMobile && mobileOpen" class="overlay" @click="mobileOpen = false" />
  </Transition>

  <!-- Sidebar -->
  <Transition name="sidebar-slide">
    <aside
      v-show="!isMobile || mobileOpen"
      class="sidebar"
      :class="{
        collapsed: sidebarCollapsed && !isMobile,
        mobile: isMobile,
        'mobile-open': mobileOpen,
      }"
    >
      <!-- Logo -->
      <div class="sidebar-logo" @click="toggleCollapse" role="button" tabindex="0" aria-label="Toggle sidebar">
        <span class="logo-icon">●</span>
        <Transition name="fade">
          <span v-if="!sidebarCollapsed || isMobile" class="logo-text">ComoBot</span>
        </Transition>
      </div>

      <!-- Menu -->
      <nav class="sidebar-menu">
        <template v-for="item in menuItems" :key="item.key">
          <div v-if="item.key === 'divider'" class="menu-divider" />
          <NTooltip v-else :disabled="!sidebarCollapsed || isMobile" placement="right">
            <template #trigger>
              <button
                class="menu-item"
                :class="{ active: isActive(item.key!) }"
                @click="navigate(item.key!)"
                :aria-label="item.label"
              >
                <span class="menu-icon" aria-hidden="true">{{ item.icon }}</span>
                <Transition name="fade">
                  <span v-if="!sidebarCollapsed || isMobile" class="menu-label">{{ item.label }}</span>
                </Transition>
              </button>
            </template>
            {{ item.label }}
          </NTooltip>
        </template>
      </nav>

      <!-- Bottom -->
      <div class="sidebar-bottom">
        <StatusBadge v-if="!sidebarCollapsed || isMobile" :status="agentStatus || 'offline'" />
        <div class="sidebar-actions">
          <NTooltip :disabled="!sidebarCollapsed || isMobile" placement="right">
            <template #trigger>
              <button class="action-btn" @click="themeStore.toggle()" :aria-label="themeStore.isDark ? 'Switch to light mode' : 'Switch to dark mode'">
                {{ themeStore.isDark ? '☀' : '☾' }}
              </button>
            </template>
            {{ themeStore.isDark ? 'Light mode' : 'Dark mode' }}
          </NTooltip>
          <NTooltip :disabled="!sidebarCollapsed || isMobile" placement="right">
            <template #trigger>
              <button class="action-btn logout-btn" @click="handleLogout" aria-label="Logout">
                ⏻
              </button>
            </template>
            Logout
          </NTooltip>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-width);
  background: var(--bg-subtle);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 100;
  transition: width 200ms var(--ease-default);
  overflow: hidden;
}
.sidebar.collapsed {
  width: var(--sidebar-collapsed);
}
.sidebar.mobile {
  width: 280px;
  transform: translateX(-100%);
  transition: transform 300ms var(--ease-enter);
}
.sidebar.mobile-open {
  transform: translateX(0);
}

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
}
.overlay-fade-enter-active,
.overlay-fade-leave-active {
  transition: opacity 200ms;
}
.overlay-fade-enter-from,
.overlay-fade-leave-to {
  opacity: 0;
}

.sidebar-slide-enter-active,
.sidebar-slide-leave-active {
  transition: transform 300ms var(--ease-enter);
}

.hamburger {
  position: fixed;
  top: 12px;
  left: 12px;
  z-index: 98;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 20px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.sidebar-logo {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-5);
  cursor: pointer;
  user-select: none;
  min-height: 56px;
}
.logo-icon {
  font-size: 18px;
  color: var(--text-primary);
  flex-shrink: 0;
}
.logo-text {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.sidebar-menu {
  flex: 1;
  padding: var(--space-2) var(--space-3);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.menu-divider {
  height: 1px;
  background: var(--border);
  margin: var(--space-2) var(--space-3);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-base);
  font-weight: 400;
  cursor: pointer;
  transition: background 150ms var(--ease-default), color 150ms var(--ease-default);
  position: relative;
  text-align: left;
  white-space: nowrap;
  font-family: inherit;
}
.menu-item:hover {
  background: var(--bg-muted);
  color: var(--text-primary);
}
.menu-item.active {
  background: var(--bg-muted);
  color: var(--text-primary);
  font-weight: 500;
}
.menu-item.active::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 16px;
  background: var(--text-primary);
  border-radius: 1px;
}

.menu-icon {
  font-size: 16px;
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}
.menu-label {
  white-space: nowrap;
}

.sidebar-bottom {
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.sidebar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.action-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color 150ms, background 150ms;
}
.action-btn:hover {
  color: var(--text-primary);
  background: var(--bg-muted);
}
.logout-btn:hover {
  color: var(--accent-red);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
