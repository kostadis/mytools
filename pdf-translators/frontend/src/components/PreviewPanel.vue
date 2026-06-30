<script setup lang="ts">
import { ref, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { useEditor } from '../stores/editor'

const store = useEditor()
const scroller = ref<InstanceType<typeof RecycleScroller> | null>(null)

// Scroll the preview to the heading matching the current tree selection.
watch(
  () => store.selected,
  (sel) => {
    if (sel < 0) return
    const pos = store.headings.findIndex((h) => h.idx === sel)
    if (pos >= 0) scroller.value?.scrollToItem(pos)
  },
)
</script>

<template>
  <div class="prev-panel">
    <RecycleScroller
      ref="scroller"
      class="scroller"
      :items="store.headings"
      :item-size="24"
      key-field="idx"
      v-slot="{ item }"
    >
      <div
        class="pline"
        :class="{ ph: item.idx === store.selected }"
        :style="{ paddingLeft: 16 + (item.level - 1) * 12 + 'px' }"
        @click="store.select(item.idx)"
      >
        {{ '#'.repeat(item.level) }} {{ item.text }}
      </div>
    </RecycleScroller>
  </div>
</template>
