<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAdventure } from '../../stores/adventure'
import type { BlockNode, TreeValue } from '../../lib/adventureTree'
import { parseStatblockText, parseTableText, type ParsedTable, type ParsedStatblock } from '../../lib/blockParse'
import { joinLines } from '../../lib/textUtils'

const store = useAdventure()

const BLOCK_TYPES = [
  { value: 'section', label: 'Section (top-level chapter)' },
  { value: 'entries', label: 'Entries (subsection with heading)' },
  { value: 'text', label: 'Text (paragraph)' },
  { value: 'inset', label: 'Inset (sidebar box)' },
  { value: 'insetReadaloud', label: 'Read-Aloud Box' },
  { value: 'table', label: 'Table (paste tab/pipe-separated)' },
  { value: 'statblock', label: 'Stat Block (paste text)' },
  { value: 'list', label: 'List' },
  { value: 'quote', label: 'Quote' },
  { value: 'image', label: 'Image' },
  { value: 'hr', label: 'Horizontal Rule' },
] as const

const visible = ref(false)
const mode = ref<'sibling' | 'child'>('sibling')
const targetPk = ref('')

const blockType = ref('entries')
const name = ref('')
const pasteText = ref('')

function open(m: 'sibling' | 'child', pk: string) {
  mode.value = m
  targetPk.value = pk
  blockType.value = 'entries'
  name.value = ''
  pasteText.value = ''
  visible.value = true
}
defineExpose({ open })

function close() {
  visible.value = false
}

const showName = computed(() => ['section', 'entries', 'inset', 'table', 'statblock'].includes(blockType.value))
const showPaste = computed(() =>
  ['table', 'statblock', 'insetReadaloud', 'text'].includes(blockType.value),
)
const pastePlaceholder = computed(() =>
  blockType.value === 'text' ? 'Enter paragraph text...' : 'Enter read-aloud text...',
)

const parsedTable = computed<ParsedTable | null>(() =>
  blockType.value === 'table' && pasteText.value.trim() ? parseTableText(pasteText.value) : null,
)
const parsedStatblock = computed<ParsedStatblock | null>(() =>
  blockType.value === 'statblock' && pasteText.value.trim() ? parseStatblockText(pasteText.value) : null,
)

function buildNode(): TreeValue {
  const n = name.value.trim()
  const text = pasteText.value.trim()

  switch (blockType.value) {
    case 'section':
      return { type: 'section', name: n || 'New Section', entries: [] }
    case 'entries':
      return { type: 'entries', name: n || 'New Heading', entries: [] }
    case 'inset':
      return { type: 'inset', name: n || 'Sidebar', entries: [] }
    case 'insetReadaloud':
      return { type: 'insetReadaloud', entries: text ? text.split('\n').filter((l) => l.trim()) : ['Read-aloud text.'] }
    case 'text':
      return text || 'New paragraph text'
    case 'list':
      return { type: 'list', items: ['Item 1'] }
    case 'hr':
      return { type: 'hr' }
    case 'image':
      return { type: 'image', href: { type: 'internal', path: '' }, title: n }
    case 'quote':
      return { type: 'quote', entries: text ? text.split('\n').filter((l) => l.trim()) : ['Quote text.'], by: '', from: '' }
    case 'table': {
      const parsed = text ? parseTableText(text) : null
      const node: BlockNode = parsed
        ? { type: 'table', colLabels: parsed.colLabels, colStyles: parsed.colLabels.map(() => ''), rows: parsed.rows }
        : { type: 'table', colLabels: ['Column 1', 'Column 2'], colStyles: ['', ''], rows: [['', '']] }
      if (n) node.caption = n
      return node
    }
    case 'statblock': {
      const parsed = text ? parseStatblockText(text) : { rows: [], traits: [] }
      const children: TreeValue[] = []
      if (parsed.rows.length > 0) {
        children.push({ type: 'table', colLabels: ['Attribute', 'Value'], colStyles: ['', ''], rows: parsed.rows })
      }
      for (const trait of parsed.traits) {
        if (trait.name) children.push({ type: 'entries', name: trait.name, entries: trait.text ? [trait.text] : [] })
        else if (trait.text) children.push(trait.text)
      }
      return { type: 'entries', name: n || 'Stat Block', entries: children }
    }
    default:
      return 'New paragraph text'
  }
}

function confirm() {
  const node = buildNode()
  if (mode.value === 'sibling') store.addSibling(targetPk.value, node)
  else store.addChild(targetPk.value, node)
  close()
}
</script>

<template>
  <div v-if="visible" class="modal-backdrop" @click.self="close" @keydown.esc="close">
    <div class="modal-box">
      <div class="modal-header">
        <h6>Add Block</h6>
        <button class="modal-close" @click="close">✕</button>
      </div>
      <div class="modal-body">
        <label>Block Type</label>
        <select v-model="blockType">
          <option v-for="t in BLOCK_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>

        <template v-if="showName">
          <label>Name</label>
          <input v-model="name" placeholder="Section or entry name..." />
        </template>

        <template v-if="showPaste">
          <label>Content (paste text)</label>
          <textarea v-model="pasteText" rows="8" :placeholder="pastePlaceholder" />

          <div v-if="blockType === 'table'" class="parse-preview">
            <small v-if="parsedTable" class="preview-ok">
              Parsed table: {{ parsedTable.colLabels.length }} columns, {{ parsedTable.rows.length }} rows
            </small>
            <small v-else-if="pasteText.trim()" class="preview-warn">
              Could not parse as table. Try tab-separated or pipe-separated format.
            </small>
          </div>
          <div v-if="blockType === 'statblock' && parsedStatblock" class="parse-preview">
            <small class="preview-ok">
              Parsed stat block: {{ parsedStatblock.rows.length }} attribute(s), {{ parsedStatblock.traits.length }} trait(s)/action(s)
            </small>
          </div>

          <button class="btn-info" title="Join broken lines into one paragraph" @click="pasteText = joinLines(pasteText)">
            Join lines
          </button>
        </template>
      </div>
      <div class="modal-footer">
        <button @click="close">Cancel</button>
        <button class="btn-primary" @click="confirm">Add</button>
      </div>
    </div>
  </div>
</template>
