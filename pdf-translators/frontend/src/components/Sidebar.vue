<script setup lang="ts">
export type EditorId = 'markdown' | 'adventure'

interface EditorEntry {
  id: EditorId
  label: string
  icon: string
}

const EDITORS: EditorEntry[] = [
  { id: 'markdown', label: 'Markdown Editor', icon: '📝' },
  { id: 'adventure', label: 'Adventure Editor', icon: '📖' },
]

const props = defineProps<{ active: EditorId }>()
const emit = defineEmits<{ select: [EditorId] }>()
</script>

<template>
  <div class="sidebar">
    <button
      v-for="e in EDITORS"
      :key="e.id"
      class="sidebar-item"
      :class="{ active: e.id === props.active }"
      @click="emit('select', e.id)"
    >
      <span class="sidebar-icon">{{ e.icon }}</span>
      <span class="sidebar-label">{{ e.label }}</span>
    </button>
  </div>
</template>
