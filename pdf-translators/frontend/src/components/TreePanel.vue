<script setup lang="ts">
import { computed, ref, nextTick, watch } from 'vue'
import { RecycleScroller } from 'vue-virtual-scroller'
import { useEditor } from '../stores/editor'
import { hasChildren, prevSibling, nextSibling } from '../lib/tree'

const store = useEditor()

interface Row {
  idx: number
  level: number
  text: string
  indent: number
  badge: string
  hasKids: boolean
  collapsed: boolean
  canUp: boolean
  canDown: boolean
}

// Build the flat row list for the visible (un-collapsed) indices. Cheap to
// build for all rows; the scroller only mounts the ~40 that are on screen.
const rows = computed<Row[]>(() =>
  store.visible.map((idx) => {
    const b = store.blocks[idx]
    return {
      idx,
      level: b.level,
      text: b.text,
      indent: (b.level > 0 ? b.level - 1 : 0) * 14 + 4,
      badge: b.level === 0 ? 'P' : 'L' + b.level,
      hasKids: b.level > 0 && hasChildren(store.blocks, idx),
      collapsed: store.collapsed.has(idx),
      canUp: prevSibling(store.blocks, idx) >= 0,
      canDown: nextSibling(store.blocks, idx) >= 0,
    }
  }),
)

const scroller = ref<InstanceType<typeof RecycleScroller> | null>(null)
const editingIdx = ref<number>(-1)
const editValue = ref('')
const editInput = ref<HTMLInputElement | null>(null)

function onSelect(idx: number) {
  store.select(idx)
}

function startEdit(row: Row) {
  if (row.level === 0) return
  editingIdx.value = row.idx
  editValue.value = row.text
  nextTick(() => editInput.value?.focus())
}

function commitEdit() {
  if (editingIdx.value < 0) return
  store.renameHeading(editingIdx.value, editValue.value)
  editingIdx.value = -1
}

function cancelEdit() {
  editingIdx.value = -1
}

// Keep the selected tree row in view when selection changes from elsewhere
// (keyboard nav, move ops). Position in the *visible* list, not block index.
watch(
  () => store.selected,
  (sel) => {
    if (sel < 0) return
    const pos = store.visible.indexOf(sel)
    if (pos >= 0) scroller.value?.scrollToItem(pos)
  },
)
</script>

<template>
  <div class="tree-panel">
    <RecycleScroller
      ref="scroller"
      class="scroller"
      :items="rows"
      :item-size="26"
      key-field="idx"
      v-slot="{ item }"
    >
      <div
        class="hrow"
        :class="{ selected: item.idx === store.selected, editing: item.idx === editingIdx }"
        :style="{ paddingLeft: item.indent + 'px' }"
        @click="onSelect(item.idx)"
      >
        <span
          class="hrow-toggle"
          @click.stop="item.hasKids && store.toggleCollapse(item.idx)"
        >{{ item.hasKids ? (item.collapsed ? '▶' : '▼') : '' }}</span>

        <span class="hrow-badge" :class="'lvl-' + Math.min(item.level, 6)">{{ item.badge }}</span>

        <span class="hrow-text" :title="item.text" @dblclick.stop="startEdit(item)">
          <input
            v-if="item.idx === editingIdx"
            ref="editInput"
            v-model="editValue"
            @keydown.enter.prevent="commitEdit"
            @keydown.esc.prevent="cancelEdit"
            @blur="commitEdit"
            @click.stop
          />
          <template v-else>{{ item.level === 0 ? '(preamble)' : item.text || '(empty)' }}</template>
        </span>

        <span v-if="item.level > 0" class="hrow-acts">
          <button title="Promote" :disabled="item.level <= 1" @click.stop="store.promote(item.idx)">◀</button>
          <button title="Demote" :disabled="item.level >= 6" @click.stop="store.demote(item.idx)">▶</button>
          <button title="Move up" :disabled="!item.canUp" @click.stop="store.moveUp(item.idx)">↑</button>
          <button title="Move down" :disabled="!item.canDown" @click.stop="store.moveDown(item.idx)">↓</button>
          <button class="btn-del" title="Delete section" @click.stop="store.remove(item.idx)">✕</button>
        </span>
      </div>
    </RecycleScroller>
  </div>
</template>
