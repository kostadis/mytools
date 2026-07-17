<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdventure } from '../../stores/adventure'
import * as Tree from '../../lib/adventureTree'

const props = defineProps<{ pk: string }>()
const store = useAdventure()

const node = computed(() => Tree.getByPath(store.data, Tree.parsePath(props.pk)) as Tree.BlockNode)

const caption = ref('')
const colLabels = ref<string[]>([])
const rows = ref<string[][]>([])

function resetFromNode() {
  caption.value = node.value.caption || ''
  colLabels.value = [...(node.value.colLabels || [])]
  rows.value = (node.value.rows || []).map((r) => [...r])
}
resetFromNode()
watch(() => props.pk, resetFromNode)

// Structural ops commit immediately (keepOpen) against canonical data, then
// re-sync the buffered form from the result — matches the original, which
// re-rendered the whole form from state after every structural change
// (any unsaved caption/cell edits are discarded, same as before).
function addRow() {
  store.commitNode(
    props.pk,
    'Add table row',
    (n: Tree.BlockNode) => {
      if (!n.rows) n.rows = []
      const cols = (n.colLabels || []).length || 2
      n.rows.push(new Array(cols).fill(''))
    },
    true,
  )
  resetFromNode()
}

function deleteRow(r: number) {
  store.commitNode(
    props.pk,
    'Delete table row',
    (n: Tree.BlockNode) => {
      n.rows?.splice(r, 1)
    },
    true,
  )
  resetFromNode()
}

function addCol() {
  store.commitNode(
    props.pk,
    'Add table column',
    (n: Tree.BlockNode) => {
      if (!n.colLabels) n.colLabels = []
      n.colLabels.push('New Column')
      for (const row of n.rows || []) row.push('')
    },
    true,
  )
  resetFromNode()
}

function commit() {
  store.commitNode(props.pk, 'Edit table', (n: Tree.BlockNode) => {
    const cap = caption.value.trim()
    if (cap) n.caption = cap
    else delete n.caption
    n.colLabels = [...colLabels.value]
    n.rows = rows.value.map((r) => [...r])
  })
}

function cancel() {
  store.cancelEdit()
}
</script>

<template>
  <div class="table-editor" @keydown.stop @click.stop>
    <label>Caption</label>
    <input v-model="caption" />
    <table>
      <thead>
        <tr>
          <th v-for="(_, c) in colLabels" :key="c"><input v-model="colLabels[c]" /></th>
          <th class="tbl-add-col"><button title="Add column" @click="addCol">+</button></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, r) in rows" :key="r">
          <td v-for="(_, c) in colLabels" :key="c">
            <input
              v-model="row[c]"
              @focus="store.setLastActiveTextarea($event.target as HTMLInputElement)"
            />
          </td>
          <td><button class="btn-del" @click="deleteRow(r)">×</button></td>
        </tr>
      </tbody>
    </table>
    <div class="edit-actions">
      <button @click="addRow">+ Row</button>
      <button class="btn-primary ml-auto" @click="commit">Done</button>
      <button @click="cancel">Cancel</button>
    </div>
  </div>
</template>
