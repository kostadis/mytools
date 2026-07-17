<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useAdventure } from '../../stores/adventure'
import PreviewNode from './PreviewNode.vue'

const store = useAdventure()
const panel = ref<HTMLDivElement | null>(null)

// Scroll the preview to whatever the tree selection points at — not
// virtualized (preview blocks are variable-height rich content, not fixed
// rows), so this is a plain DOM query + scrollIntoView.
watch(
  () => store.selectedPath,
  async (pk) => {
    if (!pk) return
    await nextTick()
    const el = panel.value?.querySelector(`[data-pv-path="${CSS.escape(pk)}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  },
)
</script>

<template>
  <div ref="panel" class="apv-root">
    <div v-if="!store.data.length" class="apv-empty">Preview will appear here</div>
    <PreviewNode v-for="(node, i) in store.data" :key="i" :node="node" :path="[i]" :depth="0" />
  </div>
</template>
