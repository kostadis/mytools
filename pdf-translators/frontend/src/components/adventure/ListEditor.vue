<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdventure } from '../../stores/adventure'
import * as Tree from '../../lib/adventureTree'

const props = defineProps<{ pk: string }>()
const store = useAdventure()

const node = computed(() => Tree.getByPath(store.data, Tree.parsePath(props.pk)) as Tree.BlockNode)

const items = ref<string[]>([])

function resetFromNode() {
  items.value = ((node.value.items as unknown[]) || []).map((it) =>
    typeof it === 'string' ? it : JSON.stringify(it),
  )
}
resetFromNode()
watch(() => props.pk, resetFromNode)

function addItem() {
  store.commitNode(
    props.pk,
    'Add list item',
    (n: Tree.BlockNode) => {
      if (!n.items) n.items = []
      ;(n.items as unknown[]).push('')
    },
    true,
  )
  resetFromNode()
}

function deleteItem(i: number) {
  store.commitNode(
    props.pk,
    'Delete list item',
    (n: Tree.BlockNode) => {
      ;(n.items as unknown[])?.splice(i, 1)
    },
    true,
  )
  resetFromNode()
}

// Commit replaces items wholesale with the current buffered text values —
// matches the original: any non-string item still present gets flattened
// to its JSON-string form once you click Done.
function commit() {
  store.commitNode(props.pk, 'Edit list', (n: Tree.BlockNode) => {
    n.items = [...items.value]
  })
}

function cancel() {
  store.cancelEdit()
}
</script>

<template>
  <div class="list-editor" @keydown.stop @click.stop>
    <label>List items</label>
    <div v-for="(_, i) in items" :key="i" class="list-item-row">
      <input v-model="items[i]" @focus="store.setLastActiveTextarea($event.target as HTMLInputElement)" />
      <button class="btn-del" @click="deleteItem(i)">×</button>
    </div>
    <div class="edit-actions">
      <button @click="addItem">+ Item</button>
      <button class="btn-primary ml-auto" @click="commit">Done</button>
      <button @click="cancel">Cancel</button>
    </div>
  </div>
</template>
