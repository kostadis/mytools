<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore } from '../stores/library'

const store = useLibraryStore()
const router = useRouter()
const searchAll = ref('')
const searchName = ref('')

onMounted(async () => {
  await store.loadFilters()
  await store.search()
})

function doSearch() {
  store.setQuery(searchAll.value, searchName.value)
}

function onFilterChange(key: string, event: Event) {
  const val = (event.target as HTMLSelectElement).value
  store.setFilter(key, val)
}

function onTagClick(tag: string) {
  store.setFilter('tags', tag)
}

function goToBook(id: number) {
  router.push({ name: 'book', params: { id } })
}

function pageRange(): number[] {
  const pages: number[] = []
  const start = Math.max(1, store.page - 2)
  const end = Math.min(store.totalPages, store.page + 2)
  for (let i = start; i <= end; i++) pages.push(i)
  return pages
}

function sortIcon(field: string): string {
  if (store.sortField !== field) return ''
  return store.sortDir === 'asc' ? ' \u25B2' : ' \u25BC'
}

const columns = [
  { key: 'title', label: 'Title' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'game_system', label: 'System' },
  { key: 'product_type', label: 'Type' },
  { key: 'series', label: 'Series' },
  { key: 'page_count', label: 'Pages' },
  { key: 'source', label: 'Source' },
]

const TAG_GROUPS: { label: string; tags: string[] }[] = [
  {
    label: 'Content',
    tags: ['monsters', 'encounters', 'combat', 'traps', 'dragons',
           'spells', 'subclasses', 'feats', 'races', 'classes', 'backgrounds',
           'skills', 'equipment', 'weapons', 'vehicles',
           'npc', 'factions', 'lore', 'worldbuilding', 'treasure',
           'random_tables', 'rules', 'crafting', 'character_creation',
           'names', 'locations', 'undead', 'lair',
           'dungeon', 'wilderness', 'urban', 'naval', 'planar',
           'maps', 'battlemaps', 'hexcrawl', 'sandbox', 'mega_dungeon',
           'handouts', 'tokens', 'miniatures', 'player_aid',
           'fillable', 'print_and_play', 'cards',
           'one_shot', 'campaign', 'solo_play', 'organized_play'],
  },
  {
    label: 'Genre',
    tags: ['horror', 'sci_fi', 'cyberpunk', 'steampunk', 'historical',
           'mystery', 'dark_fantasy', 'humor'],
  },
  {
    label: 'System',
    tags: ['5e', '5e_2024', '3_5e', '4e', 'ad_d', 'od_d', 'osr',
           'pf1e', 'pf2e', 'dcc', '13th_age', 'shadow_demon_lord',
           'castles_and_crusades', 'zweihander',
           'coc', 'fate', 'gurps', 'savage_worlds',
           'pbta', 'dungeon_world', 'blades',
           'year_zero', 'cypher', 'mothership', 'alien_rpg',
           'dragonbane', 'vtm', '2d20', 'conan', 'iron_kingdoms',
           'tinyd6', 'dune', 'system_neutral'],
  },
  {
    label: 'D&D Setting',
    tags: ['forgotten_realms', 'greyhawk', 'eberron', 'ravenloft',
           'spelljammer', 'planescape', 'dragonlance',
           'icewind_dale', 'underdark', 'waterdeep'],
  },
]

function tagGroups(available: { value: string; count: number }[]) {
  const avail = new Map(available.map(f => [f.value, f.count]))
  return TAG_GROUPS
    .map(group => ({
      label: group.label,
      tags: group.tags
        .filter(t => avail.has(t))
        .map(t => ({ value: t, count: avail.get(t)! })),
    }))
    .filter(group => group.tags.length > 0)
}
</script>

<template>
  <div class="browse-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="filter-section">
        <label>Search All Fields</label>
        <input
          v-model="searchAll"
          type="text"
          placeholder="Search all fields..."
          class="search-input"
          @keyup.enter="doSearch"
        />
      </div>

      <div class="filter-section">
        <label>Search by Title</label>
        <input
          v-model="searchName"
          type="text"
          placeholder="Search by title/filename..."
          class="search-input"
          @keyup.enter="doSearch"
        />
      </div>

      <button class="btn-secondary search-btn" @click="doSearch">Search</button>

      <div class="filter-section" v-if="store.filters">
        <label>Tag</label>
        <select @change="onFilterChange('tags', $event)">
          <option value="">All tags</option>
          <optgroup
            v-for="group in tagGroups(store.filters.tags)"
            :key="group.label"
            :label="group.label"
          >
            <option
              v-for="f in group.tags"
              :key="f.value"
              :value="f.value"
            >{{ f.value }} ({{ f.count }})</option>
          </optgroup>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Source</label>
        <select @change="onFilterChange('source', $event)">
          <option value="">All sources</option>
          <option
            v-for="f in store.filters.source" :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Product Type</label>
        <select @change="onFilterChange('product_type', $event)">
          <option value="">All types</option>
          <option
            v-for="f in store.filters.product_type" :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Game System</label>
        <select @change="onFilterChange('game_system', $event)">
          <option value="">All systems</option>
          <option
            v-for="f in store.filters.game_system.slice(0, 30)"
            :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Publisher</label>
        <select @change="onFilterChange('publisher', $event)">
          <option value="">All publishers</option>
          <option
            v-for="f in store.filters.publisher.slice(0, 100)"
            :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Series</label>
        <select @change="onFilterChange('series', $event)">
          <option value="">All series</option>
          <option
            v-for="f in store.filters.series.slice(0, 100)"
            :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section">
        <label class="filter-heading">Show/Hide</label>
        <label class="checkbox-label">
          <input type="checkbox" :checked="store.includeDrafts" @change="store.toggleIncludeDrafts()" />
          Include drafts/WIP
        </label>
        <label class="checkbox-label">
          <input type="checkbox" :checked="store.includeDuplicates" @change="store.toggleIncludeDuplicates()" />
          Include duplicates
        </label>
        <label class="checkbox-label">
          <input type="checkbox" :checked="store.includeOld" @change="store.toggleIncludeOld()" />
          Include old versions
        </label>
      </div>

      <button class="btn-secondary clear-btn" @click="searchAll = ''; searchName = ''; store.clearFilters()">
        Clear Filters
      </button>
    </aside>

    <!-- Results -->
    <div class="results">
      <div class="results-header">
        <span class="result-count">{{ store.total.toLocaleString() }} books</span>
        <div class="header-controls">
          <span v-if="store.loading" class="loading">Loading...</span>
          <div class="view-toggle">
            <button
              :class="['btn-secondary btn-sm', { active: store.viewMode === 'table' }]"
              @click="store.viewMode = 'table'"
            >Table</button>
            <button
              :class="['btn-secondary btn-sm', { active: store.viewMode === 'cards' }]"
              @click="store.viewMode = 'cards'"
            >Cards</button>
          </div>
        </div>
      </div>

      <!-- Table View -->
      <div v-if="store.viewMode === 'table'" class="table-wrapper">
        <table class="book-table">
          <thead>
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                @click="store.toggleSort(col.key)"
                class="sortable"
              >{{ col.label }}{{ sortIcon(col.key) }}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="book in store.results" :key="book.id">
              <tr @click="goToBook(book.id)" class="book-row">
                <td class="col-title">{{ book.display_title || book.filename }}</td>
                <td>{{ book.publisher }}</td>
                <td>{{ book.game_system }}</td>
                <td><span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span></td>
                <td>{{ book.series }}</td>
                <td class="col-num">{{ book.page_count }}</td>
                <td>{{ book.source }}</td>
                <td class="col-variants">
                  <button
                    v-if="book.variant_count > 1"
                    class="variant-btn"
                    @click.stop="store.toggleGroup(book.variant_ids)"
                  >{{ store.isExpanded(book.variant_ids) ? '▾' : '▸' }} {{ book.variant_count }} files</button>
                </td>
              </tr>
              <template v-if="book.variant_count > 1 && store.isExpanded(book.variant_ids)">
                <tr
                  v-for="v in store.getVariants(book.variant_ids)"
                  :key="v.id"
                  class="book-row variant-row"
                  @click="goToBook(v.id)"
                >
                  <td class="col-title variant-title">{{ v.display_title || v.filename }}</td>
                  <td></td>
                  <td>{{ v.game_system }}</td>
                  <td><span v-if="v.product_type" class="type-badge">{{ v.product_type }}</span></td>
                  <td></td>
                  <td class="col-num">{{ v.page_count }}</td>
                  <td></td>
                  <td></td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Card View -->
      <div v-else class="book-grid">
        <div
          v-for="book in store.results"
          :key="book.id"
          class="book-card"
          @click="goToBook(book.id)"
        >
          <div class="card-title">{{ book.display_title || book.filename }}</div>
          <div class="card-meta">
            <span v-if="book.publisher" class="meta-publisher">{{ book.publisher }}</span>
            <span v-if="book.game_system" class="meta-system">{{ book.game_system }}</span>
          </div>
          <div class="card-desc" v-if="book.description">{{ book.description }}</div>
          <div class="card-tags" v-if="book.tags">
            <span
              v-for="tag in book.tags.slice(0, 6)"
              :key="tag"
              class="tag"
              @click.stop="onTagClick(tag)"
            >{{ tag }}</span>
          </div>
          <div class="card-footer">
            <span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span>
            <span v-if="book.page_count" class="page-count">{{ book.page_count }}p</span>
            <span v-if="book.series" class="series-name">{{ book.series }}</span>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div class="pagination" v-if="store.totalPages > 1">
        <button
          class="btn-secondary"
          :disabled="store.page <= 1"
          @click="store.setPage(store.page - 1)"
        >Prev</button>
        <button
          v-for="p in pageRange()"
          :key="p"
          :class="['btn-secondary', { active: p === store.page }]"
          @click="store.setPage(p)"
        >{{ p }}</button>
        <button
          class="btn-secondary"
          :disabled="store.page >= store.totalPages"
          @click="store.setPage(store.page + 1)"
        >Next</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.browse-layout {
  display: flex;
  min-height: calc(100vh - 52px);
}

.sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--bg-sidebar);
  padding: 1rem;
  border-right: 1px solid var(--border);
  overflow-y: auto;
}

.filter-section {
  margin-bottom: 1rem;
}

.filter-section label {
  display: block;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 0.25rem;
  letter-spacing: 0.05em;
}

.search-mode {
  display: flex;
  gap: 2px;
  margin-bottom: 0.35rem;
}

.search-mode .active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.filter-section select,
.search-input {
  width: 100%;
}

.filter-heading {
  display: block;
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--text-dim);
  margin-bottom: 0.35rem;
  letter-spacing: 0.05em;
}

.checkbox-label {
  display: flex !important;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  text-transform: none !important;
  font-size: 0.85rem !important;
  color: var(--text) !important;
  margin-bottom: 0.25rem;
}

.checkbox-label input[type="checkbox"] {
  width: auto;
}

.search-btn {
  width: 100%;
  margin-bottom: 0.5rem;
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

.search-btn:hover {
  opacity: 0.9;
}

.clear-btn {
  width: 100%;
  margin-top: 0.5rem;
}

.results {
  flex: 1;
  padding: 1rem 1.5rem;
  overflow-y: auto;
}

.results-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.result-count {
  font-size: 0.875rem;
  color: var(--text-dim);
}

.loading {
  color: var(--accent);
  font-size: 0.875rem;
}

.view-toggle {
  display: flex;
  gap: 2px;
}

.btn-sm {
  padding: 0.3rem 0.6rem;
  font-size: 0.75rem;
}

.view-toggle .active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

/* Table View */
.table-wrapper {
  overflow-x: auto;
}

.book-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.book-table th {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 2px solid var(--border);
  color: var(--text-dim);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  user-select: none;
}

.book-table th.sortable {
  cursor: pointer;
}

.book-table th.sortable:hover {
  color: var(--accent);
}

.book-row {
  cursor: pointer;
  transition: background 0.15s;
}

.book-row:hover {
  background: var(--bg-card);
}

.book-row td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-title {
  color: var(--text-bright) !important;
  font-weight: 500;
}

.col-num {
  text-align: right;
}

.col-variants {
  white-space: nowrap;
}

.variant-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--accent);
  font-size: 0.72rem;
  padding: 0.1rem 0.4rem;
  cursor: pointer;
  white-space: nowrap;
}

.variant-btn:hover {
  background: var(--bg-card);
}

.variant-row {
  background: var(--bg-sidebar);
}

.variant-title {
  padding-left: 1.5rem !important;
  font-size: 0.8rem;
  color: var(--text) !important;
  font-weight: normal !important;
}

.type-badge {
  background: var(--accent);
  color: white;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.7rem;
  text-transform: uppercase;
}

/* Card View */
.book-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 0.75rem;
}

.book-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: border-color 0.2s;
}
.book-card:hover {
  border-color: var(--accent);
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-bright);
  margin-bottom: 0.35rem;
}

.card-meta {
  display: flex;
  gap: 0.75rem;
  font-size: 0.8rem;
  color: var(--text-dim);
  margin-bottom: 0.35rem;
}

.card-desc {
  font-size: 0.8rem;
  color: var(--text);
  margin-bottom: 0.5rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}

.card-footer {
  display: flex;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--text-dim);
}

/* Pagination */
.pagination {
  display: flex;
  gap: 0.35rem;
  justify-content: center;
  margin-top: 1.5rem;
  padding-bottom: 2rem;
}

.pagination .active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}
</style>
