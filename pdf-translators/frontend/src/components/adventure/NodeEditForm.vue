<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAdventure } from '../../stores/adventure'
import * as Tree from '../../lib/adventureTree'
import { joinLines } from '../../lib/textUtils'
import TableEditor from './TableEditor.vue'
import ListEditor from './ListEditor.vue'

const props = defineProps<{ pk: string; type: string }>()
const emit = defineEmits<{ 'add-child': [pk: string] }>()

const store = useAdventure()

const node = computed(() => Tree.getByPath(store.data, Tree.parsePath(props.pk)) as Tree.BlockNode)

const KNOWN_FLAGS = [
  { id: '1e', label: '1e stat', desc: '1st edition stat block — needs 5e conversion' },
  { id: 'review', label: 'Review', desc: 'Needs manual review' },
  { id: 'todo', label: 'TODO', desc: 'Work in progress' },
]

// ── string ───────────────────────────────────────────────────────────────
const stringText = ref('')
function resetStringText() {
  stringText.value = typeof node.value === 'string' ? (node.value as unknown as string) : ''
}
function commitString() {
  store.setNodeValue(props.pk, stringText.value, 'Edit text')
}

// ── image ────────────────────────────────────────────────────────────────
const imgTitle = ref('')
const imgHrefPath = ref('')
function resetImage() {
  imgTitle.value = node.value?.title || ''
  imgHrefPath.value = node.value?.href?.path || ''
}
function commitImage() {
  store.commitNode(props.pk, `Edit ${node.value.title || 'image'}`, (n: Tree.BlockNode) => {
    if (imgTitle.value === '') delete n.title
    else n.title = imgTitle.value
    if (!n.href) n.href = { type: 'internal' }
    n.href.path = imgHrefPath.value
  })
}

// ── quote ────────────────────────────────────────────────────────────────
const quoteEntries = ref('')
const quoteBy = ref('')
const quoteFrom = ref('')
function resetQuote() {
  quoteEntries.value = ((node.value?.entries as Tree.TreeValue[]) || [])
    .filter((e) => typeof e === 'string')
    .join('\n')
  quoteBy.value = node.value?.by || ''
  quoteFrom.value = node.value?.from || ''
}
function commitQuote() {
  store.commitNode(props.pk, 'Edit quote', (n: Tree.BlockNode) => {
    n.entries = quoteEntries.value.split('\n').filter((l) => l.length > 0)
    if (quoteBy.value === '') delete n.by
    else n.by = quoteBy.value
    if (quoteFrom.value === '') delete n.from
    else n.from = quoteFrom.value
  })
}

// ── generic: section / entries / inset / insetReadaloud ────────────────────
const GENERIC_TYPES = ['section', 'entries', 'inset', 'insetReadaloud']
const showName = computed(() => props.type !== 'insetReadaloud')
const genericName = ref('')
const genericType = ref('entries')
function resetGeneric() {
  genericName.value = node.value?.name || ''
  genericType.value = props.type
}
function commitGeneric() {
  store.commitNode(props.pk, `Edit ${node.value?.name || props.type}`, (n: Tree.BlockNode) => {
    if (showName.value) n.name = genericName.value
    n.type = genericType.value
  })
}

function resetAll() {
  resetStringText()
  resetImage()
  resetQuote()
  resetGeneric()
}
resetAll()
watch(() => props.pk, resetAll)

function cancel() {
  store.cancelEdit()
}

function joinLinesInto(target: 'string' | 'quote') {
  if (target === 'string') stringText.value = joinLines(stringText.value)
  else quoteEntries.value = joinLines(quoteEntries.value)
}
</script>

<template>
  <div class="anode-edit" @keydown.stop @click.stop>
    <template v-if="type === 'string'">
      <label>Text</label>
      <textarea
        v-model="stringText"
        rows="4"
        @focus="store.setLastActiveTextarea($event.target as HTMLTextAreaElement)"
      />
      <div class="edit-actions">
        <button class="btn-primary" @click="commitString">Done</button>
        <button @click="cancel">Cancel</button>
        <button class="btn-info ml-auto" title="Join broken lines into one paragraph" @click="joinLinesInto('string')">Join lines</button>
      </div>
    </template>

    <template v-else-if="type === 'hr'">
      <span class="muted">Horizontal rule (no editable fields)</span>
      <div class="edit-actions">
        <button @click="cancel">Close</button>
      </div>
    </template>

    <template v-else-if="type === 'table'">
      <TableEditor :pk="pk" />
    </template>

    <template v-else-if="type === 'list'">
      <ListEditor :pk="pk" />
    </template>

    <template v-else-if="type === 'image'">
      <label>Title</label>
      <input v-model="imgTitle" />
      <label>Path (href.path)</label>
      <input v-model="imgHrefPath" />
      <div class="edit-actions">
        <button class="btn-primary" @click="commitImage">Done</button>
        <button @click="cancel">Cancel</button>
      </div>
    </template>

    <template v-else-if="type === 'quote'">
      <label>Quote text (one paragraph per line)</label>
      <textarea
        v-model="quoteEntries"
        rows="3"
        @focus="store.setLastActiveTextarea($event.target as HTMLTextAreaElement)"
      />
      <label>By</label>
      <input v-model="quoteBy" />
      <label>From</label>
      <input v-model="quoteFrom" />
      <div class="edit-actions">
        <button class="btn-primary" @click="commitQuote">Done</button>
        <button @click="cancel">Cancel</button>
        <button class="btn-info ml-auto" title="Join broken lines into one paragraph" @click="joinLinesInto('quote')">Join lines</button>
      </div>
    </template>

    <template v-else-if="GENERIC_TYPES.includes(type)">
      <template v-if="showName">
        <label>Name</label>
        <input v-model="genericName" />
      </template>
      <label>Type</label>
      <select v-model="genericType">
        <option v-for="t in GENERIC_TYPES" :key="t" :value="t">{{ t }}</option>
      </select>
      <div class="edit-actions">
        <button class="btn-primary" @click="commitGeneric">Done</button>
        <button @click="cancel">Cancel</button>
        <button class="btn-primary ml-auto" @click="emit('add-child', pk)">+ Add child</button>
      </div>
    </template>

    <div v-if="type !== 'string' && type !== 'hr'" class="flag-toggles">
      <label>Flags</label>
      <div class="flag-toggle-row">
        <button
          v-for="f in KNOWN_FLAGS"
          :key="f.id"
          class="flag-toggle"
          :class="{ active: Tree.getNodeFlags(node).includes(f.id) }"
          :title="f.desc"
          @click="store.toggleFlag(pk, f.id)"
        >
          <span class="flag-dot" :class="'flag-' + f.id">{{ f.label }}</span>
          <template v-if="Tree.getNodeFlags(node).includes(f.id)"> ✓</template>
        </button>
      </div>
    </div>
  </div>
</template>
