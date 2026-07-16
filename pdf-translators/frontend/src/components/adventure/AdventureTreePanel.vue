<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import { useAdventure } from '../../stores/adventure'
import * as Tree from '../../lib/adventureTree'

const store = useAdventure()
const emit = defineEmits<{ 'add-sibling': [pk: string] }>()

const BADGE_LABEL: Record<string, string> = {
  section: 'SEC', entries: 'ENT', inset: 'INS', insetReadaloud: 'READ',
  list: 'LIST', table: 'TBL', image: 'IMG', quote: 'QUO', hr: 'HR', string: 'TXT',
}

function nodeLabel(node: Tree.TreeValue, type: string): string {
  if (type === 'string') return Tree.getNodeName(node)
  if (type === 'hr') return '--- horizontal rule ---'
  const n = node as Tree.BlockNode
  if (type === 'table') return n.caption || (n.colLabels || []).join(', ') || 'table'
  if (type === 'image') return n.title || n.href?.path || 'image'
  return Tree.getNodeName(node) || '(unnamed)'
}

interface Row {
  pk: string
  path: Tree.NodePath
  depth: number
  type: string
  badge: string
  label: string
  isString: boolean
  flags: string[]
  hasKids: boolean
  collapsed: boolean
  canUp: boolean
  canDown: boolean
  canPromote: boolean
  canDemote: boolean
}

const rows = computed<Row[]>(() =>
  store.visible.map((r) => {
    const type = Tree.getNodeType(r.node)
    return {
      pk: r.pk,
      path: r.path,
      depth: r.depth,
      type,
      badge: BADGE_LABEL[type] || type.slice(0, 4).toUpperCase(),
      label: nodeLabel(r.node, type),
      isString: type === 'string',
      flags: Tree.getNodeFlags(r.node),
      hasKids: Tree.hasChildren(r.node),
      collapsed: store.collapsed.has(r.pk),
      canUp: Tree.canMove(store.data, r.path, -1),
      canDown: Tree.canMove(store.data, r.path, 1),
      canPromote: Tree.canPromote(store.data, r.path),
      canDemote: Tree.canDemote(store.data, r.path),
    }
  }),
)

function onRowClick(e: MouseEvent, pk: string) {
  store.clickSelect(pk, e.ctrlKey || e.metaKey, e.shiftKey)
}

const scroller = ref<InstanceType<typeof DynamicScroller> | null>(null)

watch(
  () => store.selectedPath,
  (pk) => {
    if (!pk) return
    const pos = store.visible.findIndex((r) => r.pk === pk)
    if (pos >= 0) scroller.value?.scrollToItem(pos)
  },
)
</script>

<template>
  <div class="tree-panel">
    <DynamicScroller
      ref="scroller"
      class="scroller"
      :items="rows"
      :min-item-size="28"
      key-field="pk"
    >
      <template #default="{ item, active, index }">
        <DynamicScrollerItem :item="item" :active="active" :index="index" :watch-data="true">
          <div
            class="anode-header"
            :class="{ selected: item.pk === store.selectedPath, 'multi-selected': store.selection.has(item.pk) }"
            :style="{ paddingLeft: item.depth * 16 + 4 + 'px' }"
            @click="onRowClick($event, item.pk)"
          >
            <span
              class="anode-toggle"
              @click.stop="item.hasKids && store.toggleCollapse(item.pk)"
            >{{ item.hasKids ? (item.collapsed ? '▶' : '▼') : '' }}</span>

            <span class="anode-badge" :class="'badge-' + item.type">{{ item.badge }}</span>

            <span v-if="item.flags.length" class="anode-flags">
              <span v-for="f in item.flags" :key="f" class="flag-dot" :class="'flag-' + f">{{ f }}</span>
            </span>

            <span class="anode-label" :class="{ 'text-preview': item.isString }" :title="item.label">{{ item.label }}</span>

            <span class="anode-acts">
              <button title="Move up" :disabled="!item.canUp" @click.stop="store.moveUp(item.pk)">↑</button>
              <button title="Move down" :disabled="!item.canDown" @click.stop="store.moveDown(item.pk)">↓</button>
              <button title="Promote (move out of parent)" :disabled="!item.canPromote" @click.stop="store.promote(item.pk)">←</button>
              <button title="Demote (nest into sibling above)" :disabled="!item.canDemote" @click.stop="store.demote(item.pk)">→</button>
              <button title="Add sibling after" @click.stop="emit('add-sibling', item.pk)">+</button>
              <button v-if="item.hasKids" class="btn-dissolve" title="Dissolve (delete block, keep children)" @click.stop="store.dissolve(item.pk)">⊟</button>
              <button class="btn-del" title="Delete (block + children)" @click.stop="store.remove(item.pk)">×</button>
            </span>
          </div>

          <div v-if="item.pk === store.selectedPath" class="anode-edit-slot" @click.stop @keydown.stop>
            <slot name="edit" :pk="item.pk" :type="item.type" />
          </div>
        </DynamicScrollerItem>
      </template>
    </DynamicScroller>
  </div>
</template>
