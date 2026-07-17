<script setup lang="ts">
import { onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { useAdventure } from '../stores/adventure'
import AdventureTreePanel from '../components/adventure/AdventureTreePanel.vue'
import AdventurePreviewPanel from '../components/adventure/AdventurePreviewPanel.vue'
import NodeEditForm from '../components/adventure/NodeEditForm.vue'
import MultiSelectBar from '../components/adventure/MultiSelectBar.vue'
import TagToolbar from '../components/adventure/TagToolbar.vue'
import AddBlockModal from '../components/adventure/AddBlockModal.vue'
import HistoryDropdown from '../components/adventure/HistoryDropdown.vue'

const store = useAdventure()
const files = ref<string[]>([])
const selectedFile = ref('')
const modal = ref<InstanceType<typeof AddBlockModal> | null>(null)
const levelOpen = ref(false)

async function loadFileList() {
  const r = await fetch('/api/adv/files')
  if (r.ok) files.value = await r.json()
}

function doLoad() {
  if (selectedFile.value) store.load(selectedFile.value)
}

function onAddSibling(pk: string) {
  modal.value?.open('sibling', pk)
}
function onAddChild(pk: string) {
  modal.value?.open('child', pk)
}
function pickLevel(n: number) {
  store.expandToLevel(n)
  levelOpen.value = false
}

function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement
  if (t && ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)) return
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (store.dirty) store.save()
    return
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
    e.preventDefault()
    store.undo()
    return
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'Z' || e.key === 'y')) {
    e.preventDefault()
    store.redo()
  }
}

onMounted(() => {
  loadFileList()
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))

watchEffect(() => {
  selectedFile.value = store.currentFile
})
</script>

<template>
  <div class="editor-view">
    <div class="toolbar">
      <span class="brand">ADV</span>
      <select v-model="selectedFile" @change="doLoad">
        <option value="">Select a file...</option>
        <option v-for="f in files" :key="f" :value="f">{{ f }}</option>
      </select>
      <button class="tbtn" @click="doLoad">Load</button>
      <span class="sep"></span>
      <button class="tbtn save" title="Save (Ctrl+S)" @click="store.save()">💾 Save</button>
      <span v-if="store.dirty" class="dirty">●</span>
      <span class="sep"></span>
      <HistoryDropdown />
      <span class="sep"></span>
      <button class="tbtn" title="Collapse all" @click="store.collapseAll()">Collapse</button>
      <button class="tbtn" title="Expand all" @click="store.expandAll()">Expand</button>
      <div class="dropdown-wrap">
        <button class="tbtn" title="Expand to level..." @click="levelOpen = !levelOpen">Level</button>
        <div v-if="levelOpen" class="dropdown-menu">
          <a href="#" class="dropdown-item" @click.prevent="pickLevel(0)">Sections only</a>
          <a href="#" class="dropdown-item" @click.prevent="pickLevel(1)">Level 1</a>
          <a href="#" class="dropdown-item" @click.prevent="pickLevel(2)">Level 2</a>
          <a href="#" class="dropdown-item" @click.prevent="pickLevel(3)">Level 3</a>
        </div>
      </div>
      <span class="sep"></span>
      <span v-if="store.flagCount" class="flag-count">{{ store.flagCount }} flagged</span>
      <button class="tbtn" title="Previous flagged" @click="store.jumpToFlag(-1)">«</button>
      <button class="tbtn" title="Next flagged" @click="store.jumpToFlag(1)">»</button>
    </div>

    <div v-if="store.errorMsg" class="error-banner">
      <span>⚠ {{ store.errorMsg }}</span>
      <button @click="store.dismissError()">✕</button>
    </div>

    <div class="main">
      <div class="adv-editor-panel">
        <MultiSelectBar v-if="store.selectionCount > 0" />
        <AdventureTreePanel @add-sibling="onAddSibling">
          <template #edit="{ pk, type }">
            <NodeEditForm :pk="pk" :type="type" @add-child="onAddChild" />
          </template>
        </AdventureTreePanel>
        <div class="add-section-bar">
          <button @click="store.addTopLevelSection()">+ Add Section</button>
        </div>
        <TagToolbar />
      </div>
      <AdventurePreviewPanel />
    </div>

    <div class="status">{{ store.statusMsg }}</div>

    <AddBlockModal ref="modal" />
  </div>
</template>
