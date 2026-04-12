<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type GroupByMode } from '../stores/library'
import DimensionGrid from '../components/DimensionGrid.vue'

// Human-readable labels for the sidebar filter keys, so chips read
// "System: D&D 5e" instead of "game_system: D&D 5e".
const FILTER_LABELS: Record<string, string> = {
  game_system: 'System',
  product_type: 'Type',
  publisher: 'Publisher',
  series: 'Series',
  source: 'Source',
  tags: 'Tag',
}

interface FilterChip {
  key: string  // unique id for :key
  label: string
  value: string
  remove: () => void
  invert?: () => void   // tag chips only: flip to exclude
  excluded?: boolean    // true when this chip is an exclude chip
}

const GROUP_OPTIONS: { value: GroupByMode; label: string }[] = [
  { value: 'books',       label: 'Books' },
  { value: 'series',      label: 'Series' },
  { value: 'publisher',   label: 'Publishers' },
  { value: 'game_system', label: 'Systems' },
  { value: 'tag',         label: 'Tags' },
]

const GROUP_LABELS: Record<GroupByMode, string> = {
  books:       'books',
  series:      'series',
  publisher:   'publishers',
  game_system: 'systems',
  tag:         'tags',
}

const store = useLibraryStore()
const router = useRouter()
const searchAll = ref('')
const searchName = ref('')
const showAdvanced = ref(false)

// NLQ input — parsed results now flow into the main search state via store.applyNlq()
const nlqQuery = ref('')

function doNlqSearch() {
  const q = nlqQuery.value.trim()
  if (!q) return
  store.applyNlq(q)
}

function clearNlqBanner() {
  nlqQuery.value = ''
  store.clearNlq()
  searchAll.value = ''
  searchName.value = ''
  store.clearFilters()
}

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

const activeFilterChips = computed<FilterChip[]>(() => {
  const chips: FilterChip[] = []

  if (store.queryAll) {
    chips.push({
      key: 'q',
      label: 'Search',
      value: store.queryAll,
      remove: () => {
        searchAll.value = ''
        store.setQuery('', store.queryName)
      },
    })
  }
  if (store.queryName) {
    chips.push({
      key: 'q_name',
      label: 'Title',
      value: store.queryName,
      remove: () => {
        searchName.value = ''
        store.setQuery(store.queryAll, '')
      },
    })
  }
  for (const [k, v] of Object.entries(store.activeFilters)) {
    if (!v) continue
    const isTag = k === 'tags'
    chips.push({
      key: `filter:${k}`,
      label: FILTER_LABELS[k] || k,
      value: v,
      remove: () => store.setFilter(k, ''),
      invert: isTag ? () => { store.setFilter(k, ''); store.toggleExcludeTag(v) } : undefined,
    })
  }
  for (const tag of store.excludeTags) {
    chips.push({
      key: `exclude:${tag}`,
      label: 'Not',
      value: tag,
      remove: () => store.toggleExcludeTag(tag),
      excluded: true,
    })
  }
  if (store.charLevel !== null) {
    chips.push({
      key: 'char_level',
      label: 'Level',
      value: String(store.charLevel),
      remove: () => store.setCharLevel(null),
    })
  }
  if (store.favoritesOnly) {
    chips.push({
      key: 'favorites',
      label: 'Favorites',
      value: 'On',
      remove: () => store.setFavoritesOnly(false),
    })
  }
  return chips
})

function clearAllChips() {
  searchAll.value = ''
  searchName.value = ''
  store.clearFilters()
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
  if (store.sortField !== field) return '⇅'
  return store.sortDir === 'asc' ? '▲' : '▼'
}

const columns = [
  { key: 'title', label: 'Title' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'game_system', label: 'System' },
  { key: 'product_type', label: 'Type' },
  { key: 'min_level', label: 'Level' },
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
  <div>
    <!-- NLQ Search Bar -->
    <div class="nlq-bar">
      <div class="nlq-inner">
        <input
          v-model="nlqQuery"
          type="text"
          class="nlq-input"
          placeholder='Ask your library... e.g. "horror adventures for D&D 5e with undead"'
          @keyup.enter="doNlqSearch"
        />
        <button class="btn-primary nlq-btn" @click="doNlqSearch" :disabled="store.loading">
          {{ store.loading ? 'Searching...' : 'Ask' }}
        </button>
        <button
          v-if="nlqQuery"
          class="btn-secondary nlq-clear"
          aria-label="Clear NLQ query"
          @click="nlqQuery = ''"
        >✕</button>
      </div>
    </div>

  <div class="browse-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <!-- Search inputs -->
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

      <!-- Primary filters -->
      <div class="filter-section" v-if="store.filters">
        <label>Tag</label>
        <select @change="onFilterChange('tags', $event)" :value="store.activeFilters['tags'] ?? ''">
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
        <label>
          Game System
          <button
            type="button"
            class="filter-hint"
            title="Full system names (e.g. D&D 5e). Use Tag › System for short codes like 5e, pf1e."
            aria-label="Game System help: full system names like D&D 5e. Use Tag › System for short codes."
          >?</button>
        </label>
        <select @change="onFilterChange('game_system', $event)" :value="store.activeFilters['game_system'] ?? ''">
          <option value="">All systems</option>
          <option
            v-for="f in store.filters.game_system.slice(0, 30)"
            :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section" v-if="store.filters">
        <label>Product Type</label>
        <select @change="onFilterChange('product_type', $event)" :value="store.activeFilters['product_type'] ?? ''">
          <option value="">All types</option>
          <option
            v-for="f in store.filters.product_type" :key="f.value" :value="f.value"
          >{{ f.value }} ({{ f.count }})</option>
        </select>
      </div>

      <div class="filter-section">
        <label>Character Level</label>
        <input
          type="number" min="1" max="30" placeholder="e.g. 5"
          class="level-input"
          :value="store.charLevel ?? ''"
          @change="store.setCharLevel(($event.target as HTMLInputElement).valueAsNumber || null)"
        />
      </div>

      <!-- Advanced section -->
      <div class="advanced-section">
        <button class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <span class="adv-arrow">{{ showAdvanced ? '▾' : '▸' }}</span> Advanced
        </button>

        <div v-if="showAdvanced" class="advanced-body">
          <div class="filter-section" v-if="store.filters">
            <label>Publisher</label>
            <select @change="onFilterChange('publisher', $event)" :value="store.activeFilters['publisher'] ?? ''">
              <option value="">All publishers</option>
              <option
                v-for="f in store.filters.publisher.slice(0, 100)"
                :key="f.value" :value="f.value"
              >{{ f.value }} ({{ f.count }})</option>
            </select>
          </div>

          <div class="filter-section" v-if="store.filters">
            <label>Series</label>
            <select @change="onFilterChange('series', $event)" :value="store.activeFilters['series'] ?? ''">
              <option value="">All series</option>
              <option
                v-for="f in store.filters.series.slice(0, 100)"
                :key="f.value" :value="f.value"
              >{{ f.value }} ({{ f.count }})</option>
            </select>
          </div>

          <div class="filter-section" v-if="store.filters">
            <label>Source</label>
            <select @change="onFilterChange('source', $event)" :value="store.activeFilters['source'] ?? ''">
              <option value="">All sources</option>
              <option
                v-for="f in store.filters.source" :key="f.value" :value="f.value"
              >{{ f.value }} ({{ f.count }})</option>
            </select>
          </div>

          <div class="filter-section">
            <label class="filter-heading">Show/Hide</label>
            <label class="checkbox-label">
              <input type="checkbox" :checked="store.favoritesOnly" @change="store.setFavoritesOnly(!store.favoritesOnly)" />
              Favorites only
            </label>
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
        </div>
      </div>

      <button class="btn-secondary clear-btn" @click="searchAll = ''; searchName = ''; store.clearFilters()">
        Clear Filters
      </button>
    </aside>

    <!-- Results -->
    <div class="results">
      <!-- NLQ applied banner — shows what NLQ parsed, allows one-click clear -->
      <div v-if="store.nlqApplied" class="nlq-applied-banner">
        <span class="banner-label">NLQ:</span>
        <span v-if="store.nlqApplied.game_system" class="nlq-chip">System: {{ store.nlqApplied.game_system }}</span>
        <span v-if="store.nlqApplied.product_type" class="nlq-chip">Type: {{ store.nlqApplied.product_type }}</span>
        <span
          v-for="tag in store.nlqApplied.tags"
          :key="tag"
          class="nlq-chip tag-chip"
        >{{ tag }}</span>
        <span v-if="store.nlqApplied.keywords" class="nlq-chip keywords-chip">"{{ store.nlqApplied.keywords }}"</span>
        <span v-if="store.nlqApplied.level_min" class="nlq-chip">Level {{ store.nlqApplied.level_min }}</span>
        <button class="nlq-clear-applied" aria-label="Clear NLQ filters" @click="clearNlqBanner">✕ Clear</button>
      </div>

      <!-- Active filters banner — visible whenever ANY filter / query / level
           is applied. Each chip has a ✕ to remove just that filter, plus a
           Clear all at the end. Makes the faceted drill-in flow legible:
           after clicking Group by Publisher → Chaosium, the chip "Publisher:
           Chaosium" sits here so the user can back out individually without
           losing their search query. -->
      <div v-if="activeFilterChips.length" class="active-filters">
        <span class="active-filters-label">Filters:</span>
        <span
          v-for="chip in activeFilterChips"
          :key="chip.key"
          class="filter-chip"
          :class="{ 'filter-chip-excluded': chip.excluded }"
        >
          <span class="chip-label">{{ chip.label }}:</span>
          <span class="chip-value" :class="{ 'chip-value-excluded': chip.excluded }">{{ chip.value }}</span>
          <button
            v-if="chip.invert"
            type="button"
            class="chip-invert"
            :aria-label="`Exclude ${chip.value} tag`"
            title="Exclude this tag"
            @click="chip.invert()"
          >≠</button>
          <button
            type="button"
            class="chip-remove"
            :aria-label="`Remove ${chip.label} filter`"
            @click="chip.remove"
          >✕</button>
        </span>
        <button
          type="button"
          class="filters-clear-all"
          @click="clearAllChips"
        >Clear all</button>
      </div>

      <div class="results-header">
        <span class="result-count">
          <span v-if="store.loading || store.facetsLoading" class="loading">Loading…</span>
          <template v-else-if="store.groupBy === 'books'">{{ store.total.toLocaleString() }} books</template>
          <template v-else-if="store.facets">
            {{ store.facets[store.groupBy].length.toLocaleString() }} {{ GROUP_LABELS[store.groupBy] }}
            across {{ store.facets.total.toLocaleString() }} books
          </template>
        </span>
        <div class="header-controls">
          <div class="view-toggle group-by-toggle">
            <span class="toggle-label">Group by:</span>
            <button
              v-for="opt in GROUP_OPTIONS"
              :key="opt.value"
              :class="['btn-secondary btn-sm', { active: store.groupBy === opt.value }]"
              @click="store.setGroupBy(opt.value)"
            >{{ opt.label }}</button>
          </div>
          <div v-if="store.groupBy === 'books'" class="view-toggle">
            <button
              :class="['btn-secondary btn-sm', { active: store.viewMode === 'table' }]"
              @click="store.setViewMode('table')"
            >Table</button>
            <button
              :class="['btn-secondary btn-sm', { active: store.viewMode === 'cards' }]"
              @click="store.setViewMode('cards')"
            >Cards</button>
          </div>
        </div>
      </div>

      <!-- Error banner -->
      <div v-if="store.searchError" class="search-error-banner">{{ store.searchError }}</div>

      <!-- Group-by dimension grid (alternative to the books table/cards view).
           Lets the user see "which series/publishers/systems/tags contain
           books that match my current search" and click in to drill. -->
      <template v-if="store.groupBy !== 'books'">
        <div v-if="store.facetsLoading && !store.facets" class="status-msg">Loading…</div>
        <div
          v-else-if="store.facets && store.facets[store.groupBy].length === 0"
          class="empty-state"
        >
          <div class="empty-icon">⊘</div>
          <div class="empty-msg">No {{ GROUP_LABELS[store.groupBy] }} match these filters</div>
          <button class="btn-secondary" @click="searchAll = ''; searchName = ''; store.clearFilters()">Clear filters</button>
        </div>
        <DimensionGrid
          v-else-if="store.facets"
          :items="store.facets[store.groupBy]"
          aria-prefix="Drill into"
          @select="val => store.drillInFacet(store.groupBy, val)"
        />
      </template>

      <!-- Table View -->
      <div v-else-if="store.viewMode === 'table'" class="table-wrapper">
        <table class="book-table">
          <thead>
            <tr>
              <th class="col-fav"></th>
              <th
                v-for="col in columns"
                :key="col.key"
                :class="['sortable', { 'sort-active': store.sortField === col.key }]"
                :aria-sort="store.sortField === col.key ? (store.sortDir === 'asc' ? 'ascending' : 'descending') : 'none'"
                tabindex="0"
                role="button"
                @click="store.toggleSort(col.key)"
                @keyup.enter="store.toggleSort(col.key)"
                @keyup.space.prevent="store.toggleSort(col.key)"
              >{{ col.label }} <span class="sort-icon">{{ sortIcon(col.key) }}</span></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <!-- Skeleton rows while loading -->
            <template v-if="store.loading">
              <tr v-for="i in 10" :key="`sk-${i}`" class="skeleton-row">
                <td></td>
                <td v-for="col in columns" :key="col.key"><span class="skeleton-cell"></span></td>
                <td></td>
              </tr>
            </template>
            <template v-else-if="store.results.length === 0">
              <tr>
                <td :colspan="columns.length + 2" class="empty-cell">
                  <div class="empty-state">
                    <div class="empty-icon">⊘</div>
                    <div class="empty-msg">No books match these filters</div>
                    <button class="btn-secondary" @click="searchAll = ''; searchName = ''; store.clearFilters()">Clear filters</button>
                  </div>
                </td>
              </tr>
            </template>
            <template v-else>
            <template v-for="book in store.results" :key="book.id">
              <tr
                class="book-row"
                tabindex="0"
                role="link"
                :aria-label="`Open ${book.display_title || book.filename}`"
                @click="goToBook(book.id)"
                @keyup.enter="goToBook(book.id)"
                @keyup.space.prevent="goToBook(book.id)"
              >
                <td class="col-fav" @click.stop>
                  <button
                    class="fav-btn"
                    :class="{ 'is-fav': book.is_favorite }"
                    :aria-label="book.is_favorite ? 'Remove from favorites' : 'Add to favorites'"
                    @click="store.toggleFavorite(book.id)"
                  >{{ book.is_favorite ? '\u2665' : '\u2661' }}</button>
                </td>
                <td class="col-title">{{ book.display_title || book.filename }}</td>
                <td>{{ book.publisher }}</td>
                <td>{{ book.game_system }}</td>
                <td><span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span></td>
                <td class="col-num">
                  <span v-if="book.min_level">{{ book.min_level === book.max_level ? book.min_level : `${book.min_level}–${book.max_level}` }}</span>
                </td>
                <td>{{ book.series }}</td>
                <td class="col-num">{{ book.page_count }}</td>
                <td>{{ book.source }}</td>
                <td class="col-variants">
                  <button
                    v-if="book.variant_count > 1"
                    class="variant-btn"
                    :aria-expanded="store.isExpanded(book.variant_ids)"
                    :aria-label="`${store.isExpanded(book.variant_ids) ? 'Hide' : 'Show'} ${book.variant_count} variant files`"
                    @click.stop="store.toggleGroup(book.variant_ids)"
                  >{{ store.isExpanded(book.variant_ids) ? '▾' : '▸' }} {{ book.variant_count }} files</button>
                </td>
              </tr>
              <template v-if="book.variant_count > 1 && store.isExpanded(book.variant_ids)">
                <tr
                  v-for="v in store.getVariants(book.variant_ids)"
                  :key="v.id"
                  class="book-row variant-row"
                  tabindex="0"
                  role="link"
                  :aria-label="`Open ${v.filename}`"
                  @click="goToBook(v.id)"
                  @keyup.enter="goToBook(v.id)"
                  @keyup.space.prevent="goToBook(v.id)"
                >
                  <td class="col-fav" @click.stop>
                    <button
                      class="fav-btn"
                      :class="{ 'is-fav': v.is_favorite }"
                      :aria-label="v.is_favorite ? 'Remove from favorites' : 'Add to favorites'"
                      @click="store.toggleFavorite(v.id)"
                    >{{ v.is_favorite ? '\u2665' : '\u2661' }}</button>
                  </td>
                  <td class="col-title variant-title">{{ v.filename }}</td>
                  <td></td>
                  <td>{{ v.game_system }}</td>
                  <td><span v-if="v.product_type" class="type-badge">{{ v.product_type }}</span></td>
                  <td class="col-num">
                    <span v-if="v.min_level">{{ v.min_level === v.max_level ? v.min_level : `${v.min_level}–${v.max_level}` }}</span>
                  </td>
                  <td></td>
                  <td class="col-num">{{ v.page_count }}</td>
                  <td></td>
                  <td></td>
                </tr>
              </template>
            </template>
            </template>
          </tbody>
        </table>
      </div>

      <!-- Card View -->
      <div v-else>
        <div class="book-grid">
          <router-link
            v-for="book in store.results"
            :key="book.id"
            class="book-card"
            :to="{ name: 'book', params: { id: book.id } }"
          >
            <button
              class="card-fav-btn fav-btn"
              :class="{ 'is-fav': book.is_favorite }"
              :aria-label="book.is_favorite ? 'Remove from favorites' : 'Add to favorites'"
              @click.stop.prevent="store.toggleFavorite(book.id)"
            >{{ book.is_favorite ? '\u2665' : '\u2661' }}</button>
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
                @click.stop.prevent="onTagClick(tag)"
              >{{ tag }}</span>
            </div>
            <div class="card-footer">
              <span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span>
              <span v-if="book.page_count" class="page-count">{{ book.page_count }}p</span>
              <span v-if="book.series" class="series-name">{{ book.series }}</span>
            </div>
          </router-link>
        </div>
        <div v-if="!store.loading && store.results.length === 0" class="empty-state">
          <div class="empty-icon">⊘</div>
          <div class="empty-msg">No books match these filters</div>
          <button class="btn-secondary" @click="searchAll = ''; searchName = ''; store.clearFilters()">Clear filters</button>
        </div>
      </div>

      <!-- Pagination (books view only — facet grids show everything) -->
      <div class="pagination" v-if="store.groupBy === 'books' && store.totalPages > 1">
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
  </div>
</template>

<style scoped>
/* ── NLQ bar ── */
.nlq-bar {
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1.5rem;
}

.nlq-inner {
  display: flex;
  gap: 0.5rem;
  max-width: 900px;
}

.nlq-input {
  flex: 1;
  font-size: 0.95rem;
  padding: 0.5rem 0.75rem;
}

.nlq-btn {
  white-space: nowrap;
  padding: 0.45rem 1rem;
}

.nlq-clear {
  padding: 0.45rem 0.6rem;
}

/* NLQ applied banner */
.nlq-applied-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
  background: color-mix(in srgb, var(--accent) 8%, var(--bg-card));
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  font-size: 0.8rem;
}

.banner-label {
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 0.7rem;
  font-weight: 600;
}

.nlq-chip {
  background: var(--bg-sidebar);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.15rem 0.6rem;
  color: var(--text);
}

.tag-chip { border-color: var(--accent); color: var(--accent); }
.keywords-chip { font-style: italic; }

.nlq-clear-applied {
  margin-left: auto;
  background: none;
  border: 1px solid var(--border);
  color: var(--text-dim);
  font-size: 0.75rem;
  padding: 0.2rem 0.6rem;
  border-radius: 3px;
  cursor: pointer;
}
.nlq-clear-applied:hover { color: var(--accent); border-color: var(--accent); }

/* ── Browse layout ── */
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
.search-input,
.level-input {
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

/* Filter hint badge (button for keyboard + SR access) */
.filter-hint {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 1px solid var(--text-dim);
  font-size: 0.6rem;
  color: var(--text-dim);
  background: transparent;
  cursor: help;
  margin-left: 0.25rem;
  padding: 0;
  vertical-align: middle;
  text-transform: none;
  letter-spacing: 0;
  font-family: inherit;
}
.filter-hint:hover { color: var(--text); border-color: var(--text); }

/* Advanced section */
.advanced-section {
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
  margin-bottom: 0.75rem;
}

.advanced-toggle {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}

.advanced-toggle:hover {
  color: var(--text);
}

.adv-arrow {
  font-size: 0.65rem;
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

/* Active filters banner */
.active-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding: 0.55rem 0.75rem;
  margin-bottom: 0.75rem;
  background: color-mix(in srgb, var(--accent) 6%, var(--bg-card));
  border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  border-left: 3px solid var(--accent);
  border-radius: 4px;
  font-size: 0.8rem;
}

.active-filters-label {
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 0.7rem;
  margin-right: 0.1rem;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.4rem 0.2rem 0.55rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.78rem;
  color: var(--text);
}

.chip-label {
  color: var(--text-dim);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.chip-value {
  color: var(--text-bright);
  font-weight: 500;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-chip-excluded {
  border-color: #c0392b;
  background: color-mix(in srgb, #c0392b 8%, var(--bg-card));
}

.chip-value-excluded {
  text-decoration: line-through;
  color: #c0392b;
}

.chip-invert {
  background: transparent;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0 0.15rem;
  font-size: 0.85rem;
  line-height: 1;
}
.chip-invert:hover { color: #c0392b; }

.chip-remove {
  background: transparent;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0 0.15rem;
  font-size: 0.85rem;
  line-height: 1;
  border-radius: 3px;
}
.chip-remove:hover {
  background: var(--accent);
  color: white;
}

.filters-clear-all {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 0.25rem 0.55rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.72rem;
  margin-left: auto;
}
.filters-clear-all:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.group-by-toggle .toggle-label {
  font-size: 0.75rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-right: 0.4rem;
  align-self: center;
}

.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-dim);
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

.book-table th.sort-active {
  color: var(--accent);
}

.sort-icon {
  font-size: 0.65rem;
  margin-left: 0.2rem;
  opacity: 0.4;
}

.sort-active .sort-icon {
  opacity: 1;
}

.book-row {
  cursor: pointer;
  transition: background 0.15s;
}

.book-row:hover {
  background: var(--bg-card);
}

.book-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
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

.book-row:hover .col-title {
  text-decoration: underline;
  text-decoration-color: var(--accent);
  text-underline-offset: 2px;
}

/* Skeleton rows */
.skeleton-row td {
  padding: 0.45rem 0.75rem;
  border-bottom: 1px solid var(--border);
}

.skeleton-cell {
  display: block;
  height: 0.75rem;
  border-radius: 3px;
  background: var(--border);
  width: 70%;
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  0%   { opacity: 0.4; }
  50%  { opacity: 0.8; }
  100% { opacity: 0.4; }
}

/* Empty state */
.empty-cell {
  padding: 0 !important;
  border: none !important;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 3rem 1rem;
  color: var(--text-dim);
  text-align: center;
}

.empty-icon {
  font-size: 2.5rem;
  opacity: 0.4;
}

.empty-msg {
  font-size: 0.95rem;
}

/* Error banner */
.search-error-banner {
  padding: 0.5rem 0.75rem;
  margin-bottom: 0.75rem;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, var(--bg-card));
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
  border-radius: 4px;
  font-size: 0.875rem;
}

/* Favorite button */
.col-fav {
  width: 28px;
  text-align: center;
  padding-left: 0.4rem !important;
  padding-right: 0 !important;
}

.fav-btn {
  background: none;
  border: none;
  font-size: 1.05rem;
  color: var(--text-dim);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.fav-btn.is-fav {
  color: #e25555;
}

.fav-btn:hover {
  color: #e25555;
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
  display: block;
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: border-color 0.2s;
  color: inherit;
  text-decoration: none;
}

.card-fav-btn {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  font-size: 1.15rem;
}
.book-card:hover {
  border-color: var(--accent);
  color: inherit;
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
