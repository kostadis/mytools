<script setup lang="ts">
import { ref, onMounted, onUnmounted, watchEffect } from 'vue'
import { useEditor } from '../stores/editor'
import TreePanel from '../components/TreePanel.vue'
import PreviewPanel from '../components/PreviewPanel.vue'

const store = useEditor()
const filePath = ref(store.currentFile)

function doLoad() {
  const v = filePath.value.trim()
  if (v) store.load(v)
}

function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement
  if (t && t.tagName === 'INPUT') return

  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); store.undo(); return }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'Z' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); store.redo(); return }
  if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); store.save(); return }
  if ((e.ctrlKey || e.metaKey) && e.key === 'a') { e.preventDefault(); store.selectAllVisible(); return }
  if (e.key === 'Escape') { store.clearSelection(); return }

  const sel = store.selected
  if (sel < 0) return
  const b = store.blocks[sel]
  if (!b || b.level === 0) return

  // [ ] Del operate on the whole multi-selection (which is just {anchor} after
  // a plain click, so single-row behaviour is unchanged). Move stays single.
  if (e.key === 'u') store.moveUp(sel)
  else if (e.key === 'd') store.moveDown(sel)
  else if (e.key === '[') store.changeLevelSelected(-1)
  else if (e.key === ']') store.changeLevelSelected(1)
  else if (e.key === 'Delete') store.deleteSelected()
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// keep filePath in sync when a file is loaded from elsewhere (e.g. CLI preload)
watchEffect(() => { filePath.value = store.currentFile })
</script>

<template>
  <div class="editor-view">
    <div class="toolbar">
      <span class="brand">MD</span>
      <input
        class="file"
        type="text"
        placeholder="path/to/file.md"
        v-model="filePath"
        @keydown.enter="doLoad"
      />
      <button class="tbtn" @click="doLoad">Load</button>
      <span class="sep"></span>
      <button class="tbtn" title="Undo (Ctrl+Z)" :disabled="!store.canUndo" @click="store.undo()">↩</button>
      <button class="tbtn" title="Redo (Ctrl+Shift+Z)" :disabled="!store.canRedo" @click="store.redo()">↪</button>
      <span class="sep"></span>
      <button class="tbtn save" title="Save (Ctrl+S)" @click="store.save()">💾 Save</button>
      <span v-if="store.dirty" class="dirty">●</span>
    </div>

    <div v-if="store.errorMsg" class="error-banner">
      <span>⚠ {{ store.errorMsg }}</span>
      <button @click="store.dismissError()">✕</button>
    </div>

    <div class="main">
      <TreePanel />
      <PreviewPanel />
    </div>

    <div class="status">{{ store.statusMsg }}</div>
  </div>
</template>
