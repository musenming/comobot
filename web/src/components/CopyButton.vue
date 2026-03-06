<script setup lang="ts">
import { ref } from 'vue'
import { NButton } from 'naive-ui'

const props = defineProps<{
  text: string
  size?: 'tiny' | 'small' | 'medium' | 'large'
}>()

const copied = ref(false)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    // Clipboard API may not be available
  }
}
</script>

<template>
  <NButton :size="size || 'small'" quaternary @click="copy" :aria-label="copied ? 'Copied' : 'Copy to clipboard'">
    {{ copied ? '✓' : '⎘' }}
  </NButton>
</template>
