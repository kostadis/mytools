<script setup lang="ts">
import { computed, ref, onMounted, watchEffect } from 'vue'
import { useEditor } from './stores/editor'
import { useAdventure } from './stores/adventure'
import Sidebar, { type EditorId } from './components/Sidebar.vue'
import MarkdownEditorView from './views/MarkdownEditorView.vue'
import AdventureEditorView from './views/AdventureEditorView.vue'

const active = ref<EditorId>('markdown')
const markdownStore = useEditor()
const adventureStore = useAdventure()

onMounted(async () => {
  // Server tells us if a file was passed on the CLI, and which editor it
  // belongs to (by extension) — auto-select that editor and load the file.
  try {
    const r = await fetch('/api/config')
    if (!r.ok) return
    const cfg = await r.json()
    if (cfg.editor === 'markdown' || cfg.editor === 'adventure') active.value = cfg.editor
    if (cfg.editor === 'markdown' && cfg.path) await markdownStore.load(cfg.path)
    else if (cfg.editor === 'adventure' && cfg.path) await adventureStore.load(cfg.path)
  } catch {
    /* no config endpoint — fine */
  }
})

// Only the active view's store should drive the tab title — both views stay
// mounted (v-show), so each keeping its own document.title watcher would
// have them fight over it regardless of which one is visible.
const title = computed(() => {
  if (active.value === 'markdown') {
    const name = markdownStore.currentFile.split('/').pop() || 'Markdown Editor'
    return (markdownStore.dirty ? '● ' : '') + name
  }
  const name = adventureStore.currentFile.split('/').pop() || 'Adventure Editor'
  return (adventureStore.dirty ? '● ' : '') + name
})
watchEffect(() => {
  document.title = title.value
})
</script>

<template>
  <div class="shell">
    <Sidebar :active="active" @select="active = $event" />
    <MarkdownEditorView v-show="active === 'markdown'" />
    <AdventureEditorView v-show="active === 'adventure'" />
  </div>
</template>
