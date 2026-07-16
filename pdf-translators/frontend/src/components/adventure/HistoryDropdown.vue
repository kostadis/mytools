<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useAdventure } from '../../stores/adventure'

const store = useAdventure()
const open = ref(false)
const root = ref<HTMLDivElement | null>(null)

function toggle() {
  if (!open.value) store.refreshHistory()
  open.value = !open.value
}

function jump(idx: number) {
  store.jumpToUndo(idx)
  open.value = false
}

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

function onDocClick(e: MouseEvent) {
  if (open.value && root.value && !root.value.contains(e.target as Node)) open.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div ref="root" class="history-toolbar">
    <button title="Undo (Ctrl+Z)" :disabled="!store.canUndo" @click="store.undo()">Undo</button>
    <button title="Redo (Ctrl+Shift+Z)" :disabled="!store.canRedo" @click="store.redo()">Redo</button>
    <div class="dropdown-wrap">
      <button title="Change history" :disabled="store.undoTotal === 0" @click="toggle">History</button>
      <div v-if="open" class="dropdown-menu">
        <div v-if="store.historyEntries.length === 0" class="dropdown-empty">No history</div>
        <a
          v-for="e in [...store.historyEntries].reverse()"
          :key="e.idx"
          href="#"
          class="dropdown-item"
          :class="{ active: e.idx === store.undoPosition }"
          @click.prevent="jump(e.idx)"
        >
          <span class="hist-ts">{{ fmtTime(e.ts) }}</span>
          {{ e.action }}
        </a>
      </div>
    </div>
  </div>
</template>
