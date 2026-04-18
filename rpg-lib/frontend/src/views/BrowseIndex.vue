<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type Filters } from '../stores/library'
import DirectoryIndex from '../components/DirectoryIndex.vue'

const props = defineProps<{ type: string }>()
const store = useLibraryStore()
const router = useRouter()

const TYPE_LABELS: Record<string, string> = {
  series: 'Series',
  publisher: 'Publishers',
  game_system: 'Game Systems',
  tag: 'Tags',
}

const FILTER_KEY: Record<string, keyof Filters> = {
  series: 'series',
  publisher: 'publisher',
  game_system: 'game_system',
  tag: 'tags',
}

const filter = ref('')
const sort = ref<'count' | 'name'>('count')

const isValid = computed(() => Object.prototype.hasOwnProperty.call(TYPE_LABELS, props.type))

const items = computed(() => {
  if (!store.filters || !isValid.value) return []
  const key = FILTER_KEY[props.type]
  return store.filters[key] ?? []
})

const filtered = computed(() => {
  const q = filter.value.trim().toLowerCase()
  let list = items.value
  if (q) list = list.filter(it => it.value.toLowerCase().includes(q))
  if (sort.value === 'name') return [...list].sort((a, b) => a.value.localeCompare(b.value))
  return [...list]
})

const totalBooks = computed(() => items.value.reduce((sum, item) => sum + item.count, 0))
const typeLabel = computed(() => (TYPE_LABELS[props.type] || props.type).toLowerCase())

onMounted(async () => {
  if (!store.filters) await store.loadFilters()
})

watch(() => props.type, () => {
  filter.value = ''
  sort.value = 'count'
})

function onItemClick(name: string) {
  router.push({ name: 'topic', params: { type: props.type, name } })
}
</script>

<template>
  <div class="browse-page">
    <div class="browse-head">
      <h1 class="browse-title">Browse {{ TYPE_LABELS[props.type] || props.type }}</h1>
      <div v-if="!isValid" class="browse-sub error">
        Unknown browse type: <code>{{ props.type }}</code>. Try
        <code>/browse/series</code>, <code>/browse/publisher</code>,
        <code>/browse/game_system</code>, or <code>/browse/tag</code>.
      </div>
      <div v-else-if="store.filters" class="browse-sub">
        {{ items.length.toLocaleString() }} {{ typeLabel }} · {{ totalBooks.toLocaleString() }} books
      </div>
    </div>

    <div v-if="isValid" class="browse-tools">
      <input
        type="text"
        v-model="filter"
        class="browse-filter"
        :placeholder="`Filter ${typeLabel}…`"
        :aria-label="`Filter ${typeLabel} by name`"
      />
      <div class="browse-sort">
        <button :class="{ active: sort === 'count' }" @click="sort = 'count'">By count</button>
        <button :class="{ active: sort === 'name' }" @click="sort = 'name'">By name</button>
      </div>
    </div>

    <div v-if="!store.filters && isValid" class="status-msg">Loading…</div>

    <div v-else-if="isValid && filtered.length === 0" class="status-msg">
      <span v-if="filter">No matches for "{{ filter }}".</span>
      <span v-else>No {{ typeLabel }} in the library.</span>
    </div>

    <DirectoryIndex
      v-else-if="isValid"
      :items="filtered"
      @select="onItemClick"
    />
  </div>
</template>

<style scoped>
.browse-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 32px;
}

.browse-head {
  margin-bottom: 4px;
}

.browse-title {
  font-family: var(--font-serif);
  font-size: var(--fs-2xl);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text);
  margin: 0;
}

.browse-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
  margin-top: 4px;
}
.browse-sub.error { color: var(--danger); }
.browse-sub code {
  background: var(--chip-bg);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.browse-tools {
  display: flex;
  gap: 12px;
  margin: 16px 0;
  max-width: 900px;
  align-items: center;
}

.browse-filter {
  flex: 1;
  max-width: 420px;
}

.browse-sort {
  display: flex;
  gap: 2px;
  margin-left: auto;
}

.browse-sort button {
  background: transparent;
  border: none;
  padding: 4px 9px;
  border-radius: 5px;
  font-size: var(--fs-sm);
  color: var(--text-dim);
  cursor: pointer;
}
.browse-sort button:hover {
  background: var(--surface-alt);
  color: var(--text);
}
.browse-sort button.active {
  background: var(--chip-bg);
  color: var(--text);
  font-weight: 500;
}

.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-mute);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
}
</style>
