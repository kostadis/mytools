<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useLibraryStore } from '../stores/library'
import Chip from './Chip.vue'

const store = useLibraryStore()

const draft = ref(store.queryAll)

// Keep draft in sync if the store query changes from outside (e.g. NLQ
// populated keywords, or a clear-all reset).
watch(() => store.queryAll, (val) => {
  if (val !== draft.value) draft.value = val
})

// Map a short token key (typed by the user) to a store action.
// Returns true if the token was consumed.
const TOKEN_KEYS: Record<string, string> = {
  system: 'game_system',
  sys: 'game_system',
  type: 'product_type',
  tag: 'tags',
  pub: 'publisher',
  publisher: 'publisher',
  ser: 'series',
  series: 'series',
  src: 'source',
  source: 'source',
}

function applyToken(key: string, value: string, excluded: boolean): boolean {
  const trimmed = value.trim()
  if (!trimmed) return false
  if (key === 'level') {
    const n = Number(trimmed)
    if (!Number.isNaN(n)) {
      store.charLevel = n
      return true
    }
    return false
  }
  if (key === 'fav' || key === 'favorites') {
    store.favoritesOnly = true
    return true
  }
  const filterKey = TOKEN_KEYS[key.toLowerCase()]
  if (!filterKey) return false
  if (excluded && filterKey === 'tags') {
    if (!store.excludeTags.includes(trimmed)) {
      store.excludeTags = [...store.excludeTags, trimmed]
    }
  } else {
    store.activeFilters[filterKey] = trimmed
  }
  return true
}

// Parse tokens like `system:D&D 5e` out of the draft. Greedy on values until
// the next whitespace, so multi-word values are typed as `system:5e adventures`
// and the space ends the value (use quotes-free tokens for now). Returns the
// remaining free text.
function parseTokens(text: string): { ops: { key: string; value: string; excluded: boolean }[]; rest: string } {
  const ops: { key: string; value: string; excluded: boolean }[] = []
  const parts = text.split(/\s+/)
  const rest: string[] = []
  for (const p of parts) {
    if (!p) continue
    const m = p.match(/^(!)?([a-zA-Z_]+):(.+)$/)
    if (m) {
      ops.push({ key: m[2], value: m[3], excluded: !!m[1] })
    } else {
      rest.push(p)
    }
  }
  return { ops, rest: rest.join(' ') }
}

// True when the draft looks like a natural-language phrase: has 2+ words and
// no `key:value` tokens at all.
function looksLikeNlq(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  if (/[a-zA-Z_]+:[^\s]/.test(t)) return false
  return t.split(/\s+/).length >= 2
}

async function submit() {
  const text = draft.value.trim()
  const { ops, rest } = parseTokens(text)

  if (ops.length > 0) {
    let applied = 0
    for (const op of ops) {
      if (applyToken(op.key, op.value, op.excluded)) applied++
    }
    if (applied > 0) {
      draft.value = rest
      store.setQuery(rest, store.queryName)
      return
    }
  }

  if (looksLikeNlq(text)) {
    await store.applyNlq(text)
    // applyNlq populates store.queryAll with residual keywords; sync.
    draft.value = store.queryAll
    return
  }

  store.setQuery(text, store.queryName)
}

// When the input is empty and the user hits backspace, pop the most recent
// chip so they can quickly back out of a filter.
function maybePopChip(e: KeyboardEvent) {
  if (draft.value !== '') return
  // Order of preference for popping: free text already empty, then exclude
  // tags, then activeFilters (last inserted), then queryName.
  if (store.excludeTags.length > 0) {
    const last = store.excludeTags[store.excludeTags.length - 1]
    store.toggleExcludeTag(last)
    e.preventDefault()
    return
  }
  const keys = Object.keys(store.activeFilters)
  if (keys.length > 0) {
    const lastKey = keys[keys.length - 1]
    store.setFilter(lastKey, '')
    e.preventDefault()
    return
  }
  if (store.charLevel !== null) {
    store.setCharLevel(null)
    e.preventDefault()
    return
  }
  if (store.favoritesOnly) {
    store.setFavoritesOnly(false)
    e.preventDefault()
  }
}

const FILTER_LABELS: Record<string, string> = {
  game_system: 'system',
  product_type: 'type',
  publisher: 'pub',
  series: 'series',
  source: 'source',
  tags: 'tag',
}

interface ChipModel {
  key: string
  label: string
  value: string
  excluded?: boolean
  showInvert?: boolean
  remove: () => void
  invert?: () => void
}

const chips = computed<ChipModel[]>(() => {
  const out: ChipModel[] = []

  if (store.queryName) {
    out.push({
      key: 'q_name',
      label: 'title',
      value: store.queryName,
      remove: () => store.setQuery(store.queryAll, ''),
    })
  }

  for (const [k, v] of Object.entries(store.activeFilters)) {
    if (!v) continue
    const isTag = k === 'tags'
    out.push({
      key: `filter:${k}`,
      label: FILTER_LABELS[k] || k,
      value: v,
      remove: () => store.setFilter(k, ''),
      showInvert: isTag,
      invert: isTag ? () => { store.setFilter(k, ''); store.toggleExcludeTag(v) } : undefined,
    })
  }

  for (const tag of store.excludeTags) {
    out.push({
      key: `exclude:${tag}`,
      label: '!tag',
      value: tag,
      excluded: true,
      remove: () => store.toggleExcludeTag(tag),
    })
  }

  if (store.charLevel !== null) {
    out.push({
      key: 'level',
      label: 'level',
      value: String(store.charLevel),
      remove: () => store.setCharLevel(null),
    })
  }

  if (store.favoritesOnly) {
    out.push({
      key: 'fav',
      label: 'fav',
      value: 'on',
      remove: () => store.setFavoritesOnly(false),
    })
  }

  return out
})

const nlqActive = computed(() => store.nlqApplied !== null)

function reset() {
  draft.value = ''
  store.clearFilters()
}
</script>

<template>
  <div>
    <div class="cmd">
      <span class="cmd-glyph">⌕</span>

      <Chip
        v-for="c in chips"
        :key="c.key"
        :label="c.label"
        :value="c.value"
        :excluded="c.excluded"
        :show-invert="c.showInvert"
        @remove="c.remove"
        @invert="c.invert?.()"
      />

      <input
        v-model="draft"
        class="cmd-input"
        :placeholder="chips.length ? 'Add filter or keywords…' : 'Search or ask — e.g. &quot;horror 5e adventures with undead&quot;'"
        @keydown.enter="submit"
        @keydown.backspace="maybePopChip"
      />

      <span class="kbd">⏎</span>
    </div>

    <div class="cmd-meta">
      <span v-if="store.loading">searching…</span>
      <template v-else>
        <span v-if="nlqActive">parsed as natural language</span>
        <span v-if="nlqActive">·</span>
        <span>{{ store.total.toLocaleString() }} results</span>
      </template>
      <span>·</span>
      <button class="cmd-reset" @click="reset">reset</button>
      <span v-if="store.searchError" class="cmd-error">{{ store.searchError }}</span>
    </div>
  </div>
</template>

<style scoped>
.cmd {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface);
  border: 1px solid var(--line-hard);
  border-radius: var(--radius-lg);
  padding: 8px 10px 8px 12px;
  box-shadow: var(--shadow-1);
  flex-wrap: wrap;
}
.cmd:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-bg);
}

.cmd-glyph {
  color: var(--text-mute);
  font-size: 13px;
}

.cmd-input {
  flex: 1;
  min-width: 200px;
  border: none;
  background: transparent;
  outline: none;
  padding: 0;
  font-family: var(--font-sans);
  font-size: var(--fs-base);
  color: var(--text);
  box-shadow: none;
}
.cmd-input:focus {
  border: none;
  box-shadow: none;
}
.cmd-input::placeholder {
  color: var(--text-mute);
  font-style: italic;
}

.kbd {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-mute);
}

.cmd-meta {
  margin-top: 8px;
  display: flex;
  gap: 14px;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-mute);
  align-items: center;
}

.cmd-reset {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  color: var(--accent);
  font-family: inherit;
  font-size: inherit;
}

.cmd-error {
  margin-left: auto;
  color: var(--danger);
}
</style>
