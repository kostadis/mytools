<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type Filters } from '../stores/library'
import DimensionGrid from '../components/DimensionGrid.vue'

const props = defineProps<{ type: string }>()
const store = useLibraryStore()
const router = useRouter()

const TYPE_LABELS: Record<string, string> = {
  series: 'Series',
  publisher: 'Publishers',
  game_system: 'Game Systems',
  tag: 'Tags',
}

// Map URL :type → key inside the Filters response. Note 'tag' (singular,
// matching the topic-hub URL pattern) maps to 'tags' (plural, matching the
// /api/library/filters response shape).
const FILTER_KEY: Record<string, keyof Filters> = {
  series: 'series',
  publisher: 'publisher',
  game_system: 'game_system',
  tag: 'tags',
}

const search = ref('')
const sort = ref<'count' | 'name'>('count')

const isValid = computed(() => Object.prototype.hasOwnProperty.call(TYPE_LABELS, props.type))

const items = computed(() => {
  if (!store.filters || !isValid.value) return []
  const key = FILTER_KEY[props.type]
  return store.filters[key] ?? []
})

const filteredAndSorted = computed(() => {
  const q = search.value.trim().toLowerCase()
  let list = items.value
  if (q) {
    list = list.filter(it => it.value.toLowerCase().includes(q))
  }
  if (sort.value === 'name') {
    return [...list].sort((a, b) => a.value.localeCompare(b.value))
  }
  // 'count': API already returns by descending count, just take a copy so we
  // don't accidentally hand the store's array out.
  return [...list]
})

const totalBooks = computed(() =>
  items.value.reduce((sum, item) => sum + item.count, 0),
)

onMounted(async () => {
  if (!store.filters) await store.loadFilters()
})

// Reset the search box when switching between types so a query left over from
// "Series" doesn't silently filter "Publishers" too.
watch(() => props.type, () => {
  search.value = ''
  sort.value = 'count'
})

function onItemClick(name: string) {
  router.push({ name: 'topic', params: { type: props.type, name } })
}
</script>

<template>
  <div class="browse-page">
    <div class="browse-header">
      <h1>Browse {{ TYPE_LABELS[props.type] || props.type }}</h1>
      <div v-if="!isValid" class="browse-meta error">
        Unknown browse type: <code>{{ props.type }}</code>. Try
        <code>/browse/series</code>, <code>/browse/publisher</code>,
        <code>/browse/game_system</code>, or <code>/browse/tag</code>.
      </div>
      <div v-else-if="store.filters" class="browse-meta">
        {{ items.length.toLocaleString() }} {{ TYPE_LABELS[props.type].toLowerCase() }}
        across {{ totalBooks.toLocaleString() }} books
      </div>
    </div>

    <div v-if="isValid" class="browse-controls">
      <input
        type="text"
        v-model="search"
        :placeholder="`Filter ${TYPE_LABELS[props.type].toLowerCase()}...`"
        class="filter-input"
        :aria-label="`Filter ${TYPE_LABELS[props.type].toLowerCase()} by name`"
      />
      <div class="sort-toggle">
        <span class="sort-label">Sort:</span>
        <button
          type="button"
          :class="{ active: sort === 'count' }"
          @click="sort = 'count'"
        >By count</button>
        <button
          type="button"
          :class="{ active: sort === 'name' }"
          @click="sort = 'name'"
        >By name</button>
      </div>
    </div>

    <div v-if="!store.filters && isValid" class="status-msg">Loading...</div>

    <div
      v-else-if="isValid && filteredAndSorted.length === 0"
      class="status-msg"
    >
      <span v-if="search">No matches for "{{ search }}".</span>
      <span v-else>No {{ TYPE_LABELS[props.type].toLowerCase() }} in the library.</span>
    </div>

    <DimensionGrid
      v-else-if="isValid"
      :items="filteredAndSorted"
      @select="onItemClick"
    />
  </div>
</template>

<style scoped>
.browse-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem;
}

.browse-header h1 {
  font-size: 1.6rem;
  color: var(--text-bright);
  margin: 0 0 0.25rem;
}

.browse-meta {
  font-size: 0.85rem;
  color: var(--text-dim);
  margin-bottom: 1rem;
}

.browse-meta.error {
  color: var(--accent);
}

.browse-meta code {
  background: var(--bg-card);
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  font-size: 0.8rem;
}

.browse-controls {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.filter-input {
  flex: 1;
  min-width: 220px;
  padding: 0.5rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  font-size: 0.9rem;
}

.filter-input:focus {
  outline: none;
  border-color: var(--accent);
}

.sort-toggle {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  color: var(--text-dim);
}

.sort-label {
  margin-right: 0.1rem;
}

.sort-toggle button {
  background: var(--bg-card);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 0.3rem 0.6rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  font-family: inherit;
}

.sort-toggle button:hover {
  border-color: var(--accent);
}

.sort-toggle button.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-dim);
}

</style>
