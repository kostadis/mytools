<script setup lang="ts">
import { useAdventure } from '../../stores/adventure'

const store = useAdventure()

interface TagDef {
  tag: string
  label: string
  title: string
  style?: 'bold' | 'italic'
}

const TAGS: TagDef[] = [
  { tag: 'b', label: 'B', title: '{@b bold}', style: 'bold' },
  { tag: 'i', label: 'I', title: '{@i italic}', style: 'italic' },
  { tag: 'spell', label: 'Spell', title: '{@spell name}' },
  { tag: 'creature', label: 'Creature', title: '{@creature name}' },
  { tag: 'condition', label: 'Condition', title: '{@condition name}' },
  { tag: 'dc', label: 'DC', title: '{@dc N}' },
  { tag: 'damage', label: 'Damage', title: '{@damage XdY+Z}' },
  { tag: 'hit', label: 'Hit', title: '{@hit N}' },
  { tag: 'item', label: 'Item', title: '{@item name}' },
  { tag: 'skill', label: 'Skill', title: '{@skill name}' },
  { tag: 'atk', label: 'Atk', title: '{@atk mw}' },
  { tag: 'h', label: '@h', title: '{@h} (Hit:)' },
  { tag: 'recharge', label: 'Recharge', title: '{@recharge N}' },
]

function insertTag(tag: string) {
  const ta = store.lastActiveTextarea
  if (!ta) return
  ta.focus()
  const start = ta.selectionStart ?? 0
  const end = ta.selectionEnd ?? 0
  const sel = ta.value.substring(start, end)
  let replacement: string
  if (tag === 'h') replacement = '{@h}'
  else if (sel) replacement = `{@${tag} ${sel}}`
  else replacement = `{@${tag} }`
  ta.setRangeText(replacement, start, end, 'end')
  // With no selection, park the cursor inside the closing brace.
  if (!sel && tag !== 'h') {
    ta.selectionStart = ta.selectionEnd = start + replacement.length - 1
  }
  // v-model only syncs on a native 'input' event — setRangeText doesn't fire one.
  ta.dispatchEvent(new Event('input', { bubbles: true }))
}
</script>

<template>
  <div class="tag-bar">
    <span class="tag-bar-label">Tags:</span>
    <button v-for="t in TAGS" :key="t.tag" :title="t.title" @click="insertTag(t.tag)">
      <b v-if="t.style === 'bold'">{{ t.label }}</b>
      <i v-else-if="t.style === 'italic'">{{ t.label }}</i>
      <template v-else>{{ t.label }}</template>
    </button>
  </div>
</template>
