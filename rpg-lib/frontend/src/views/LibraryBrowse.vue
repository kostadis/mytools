<script setup lang="ts">
import { onMounted, computed, ref, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type GroupByMode } from '../stores/library'
import CommandBar from '../components/CommandBar.vue'
import FacetGroup from '../components/FacetGroup.vue'
import Checkbox from '../components/Checkbox.vue'
import DirectoryIndex from '../components/DirectoryIndex.vue'
import SubjectsDrawer from '../components/SubjectsDrawer.vue'

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

onMounted(async () => {
  await store.loadFilters()
  await store.search()
})

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
  return store.sortDir === 'asc' ? '↑' : '↓'
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

const sortLabel = computed(() => {
  if (!store.sortField) return 'relevance'
  const col = columns.find(c => c.key === store.sortField)
  return (col?.label ?? store.sortField).toLowerCase()
})

// Top tags shown directly in the rail (rest available via the Subjects drawer
// that the "Browse all tags" link will eventually open).
const topTags = computed(() => {
  if (!store.filters) return []
  return store.filters.tags.slice(0, 12)
})

const LEVEL_BUCKETS = [
  { value: '1–4',   level: 2,  label: '1–4' },
  { value: '5–10',  level: 7,  label: '5–10' },
  { value: '11–15', level: 13, label: '11–15' },
  { value: '16–20', level: 18, label: '16–20' },
]

const levelBuckets = computed(() => LEVEL_BUCKETS.map(b => ({ value: b.label, count: 0 })))

const activeLevelBucket = computed(() => {
  if (store.charLevel === null) return ''
  const lvl = store.charLevel
  if (lvl <= 4) return '1–4'
  if (lvl <= 10) return '5–10'
  if (lvl <= 15) return '11–15'
  return '16–20'
})

function setLevelBucket(label: string) {
  if (!label) {
    store.setCharLevel(null)
    return
  }
  const b = LEVEL_BUCKETS.find(b => b.label === label)
  if (b) store.setCharLevel(b.level)
}

const subjectsOpen = ref(false)

function openSubjects() {
  subjectsOpen.value = true
}

function onGlobalKey(e: KeyboardEvent) {
  // "?" opens the Subjects drawer (skip when typing in an input).
  if (e.key === '?' && !(e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement)) {
    e.preventDefault()
    subjectsOpen.value = true
  }
}

onMounted(() => window.addEventListener('keydown', onGlobalKey))
onUnmounted(() => window.removeEventListener('keydown', onGlobalKey))

function clearAll() {
  store.clearFilters()
}
</script>

<template>
  <div class="browse-layout">
    <SubjectsDrawer :open="subjectsOpen" @close="subjectsOpen = false" />
    <!-- Facet rail -->
    <aside class="rail" v-if="store.filters">
      <FacetGroup
        title="System"
        :items="store.filters.game_system.slice(0, 6)"
        :active="store.activeFilters['game_system']"
        @pick="store.setFilter('game_system', $event)"
      />
      <FacetGroup
        title="Type"
        :items="store.filters.product_type.slice(0, 6)"
        :active="store.activeFilters['product_type']"
        @pick="store.setFilter('product_type', $event)"
      />
      <FacetGroup
        title="Tags"
        :items="topTags"
        :active="store.activeFilters['tags']"
        @pick="store.setFilter('tags', $event)"
      >
        <template #footer>
          <button class="rail-more" @click="openSubjects">Browse all tags ›</button>
        </template>
      </FacetGroup>
      <FacetGroup
        title="Level"
        :items="levelBuckets"
        :active="activeLevelBucket"
        @pick="setLevelBucket"
      />

      <div class="rail-flags">
        <Checkbox
          :model-value="store.favoritesOnly"
          @update:model-value="store.setFavoritesOnly($event)"
          label="Favorites only"
        />
        <Checkbox
          :model-value="store.includeDrafts"
          @update:model-value="store.toggleIncludeDrafts()"
          label="Include drafts"
          muted
        />
        <Checkbox
          :model-value="store.includeDuplicates"
          @update:model-value="store.toggleIncludeDuplicates()"
          label="Include duplicates"
          muted
        />
        <Checkbox
          :model-value="store.includeOld"
          @update:model-value="store.toggleIncludeOld()"
          label="Include old versions"
          muted
        />
      </div>
    </aside>

    <!-- Results column -->
    <div class="results">
      <div class="cmd-wrap">
        <CommandBar />
      </div>

      <div class="results-head">
        <div class="results-count">
          <template v-if="store.groupBy === 'books'">
            <span class="num">{{ store.total.toLocaleString() }}</span>
            <span class="mute"> books · sorted by {{ sortLabel }}</span>
          </template>
          <template v-else-if="store.facets">
            <span class="num">{{ store.facets[store.groupBy].length.toLocaleString() }}</span>
            <span class="mute"> {{ GROUP_LABELS[store.groupBy] }} across {{ store.facets.total.toLocaleString() }} books</span>
          </template>
        </div>
        <div class="groupby">
          <button
            v-for="opt in GROUP_OPTIONS"
            :key="opt.value"
            :class="['pill', { active: store.groupBy === opt.value }]"
            @click="store.setGroupBy(opt.value)"
          >{{ opt.label }}</button>
          <span class="pill-sep" v-if="store.groupBy === 'books'">|</span>
          <button
            v-if="store.groupBy === 'books'"
            :class="['pill', { active: store.viewMode === 'table' }]"
            @click="store.setViewMode('table')"
          >Table</button>
          <button
            v-if="store.groupBy === 'books'"
            :class="['pill', { active: store.viewMode === 'cards' }]"
            @click="store.setViewMode('cards')"
          >Cards</button>
        </div>
      </div>

      <!-- Group-by directory list -->
      <template v-if="store.groupBy !== 'books'">
        <div v-if="store.facetsLoading && !store.facets" class="status-msg">Loading…</div>
        <div
          v-else-if="store.facets && store.facets[store.groupBy].length === 0"
          class="empty-state"
        >
          <div class="empty-icon">⊘</div>
          <div class="empty-msg">No {{ GROUP_LABELS[store.groupBy] }} match these filters</div>
          <button class="btn-secondary" @click="clearAll">Clear filters</button>
        </div>
        <div v-else-if="store.facets" class="results-body">
          <DirectoryIndex
            :items="store.facets[store.groupBy]"
            aria-prefix="Drill into"
            @select="val => store.drillInFacet(store.groupBy, val)"
          />
        </div>
      </template>

      <!-- Table -->
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
                    <button class="btn-secondary" @click="clearAll">Clear filters</button>
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

      <!-- Cards -->
      <div v-else class="results-body">
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
            <div class="card-meta-row">
              <span v-if="book.publisher">{{ book.publisher }}</span>
              <span v-if="book.publisher && book.game_system"> · </span>
              <span v-if="book.game_system">{{ book.game_system }}</span>
            </div>
            <div class="card-title">{{ book.display_title || book.filename }}</div>
            <div class="card-desc" v-if="book.description">{{ book.description }}</div>
            <div class="card-tags" v-if="book.tags && book.tags.length">
              <span
                v-for="tag in book.tags.slice(0, 6)"
                :key="tag"
                class="tag"
                @click.stop.prevent="store.setFilter('tags', tag)"
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
          <button class="btn-secondary" @click="clearAll">Clear filters</button>
        </div>
      </div>

      <!-- Pagination -->
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
</template>

<style scoped>
.browse-layout {
  display: flex;
  min-height: calc(100vh - 52px);
}

/* ── Facet rail ── */
.rail {
  width: 220px;
  min-width: 220px;
  flex-shrink: 0;
  border-right: 1px solid var(--line);
  background: var(--bg);
  padding: 16px 14px 40px;
  overflow-y: auto;
}

.rail-more {
  background: none;
  border: none;
  padding: 3px 6px;
  font-size: 11.5px;
  color: var(--accent);
  cursor: pointer;
}

.rail-flags {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* ── Results column ── */
.results {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.cmd-wrap {
  padding: 16px 20px 6px;
  border-bottom: 1px solid var(--line);
  background: var(--bg);
}

.results-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px 10px;
}

.results-count {
  font-size: var(--fs-base);
  color: var(--text-dim);
}
.results-count .num {
  color: var(--text);
  font-weight: 500;
  font-family: var(--font-mono);
}
.results-count .mute { color: var(--text-mute); }

.groupby {
  display: flex;
  gap: 2px;
  align-items: center;
}

.pill {
  padding: 4px 9px;
  font-size: var(--fs-sm);
  border-radius: 5px;
  background: transparent;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
}
.pill:hover {
  background: var(--surface-alt);
  color: var(--text);
}
.pill.active {
  background: var(--chip-bg);
  color: var(--text);
  font-weight: 500;
}

.pill-sep {
  color: var(--line-hard);
  margin: 0 4px;
}

.results-body {
  padding: 0 20px 24px;
}

/* ── Status / empty ── */
.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-mute);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
}

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
  color: var(--text-mute);
  text-align: center;
}
.empty-icon {
  font-size: 2.5rem;
  opacity: 0.4;
}
.empty-msg {
  font-size: var(--fs-md);
  color: var(--text-dim);
}

/* ── Table ── */
.table-wrapper {
  overflow-x: auto;
  padding: 0 20px 20px;
}

.book-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-base);
}

.book-table thead th {
  padding: 6px 12px;
  text-align: left;
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  border-bottom: 1px solid var(--line);
  font-weight: 400;
  white-space: nowrap;
  user-select: none;
}

.book-table th.sortable { cursor: pointer; }
.book-table th.sortable:hover { color: var(--text); }
.book-table th.sort-active { color: var(--text); }

.sort-icon {
  font-size: 10px;
  margin-left: 2px;
  color: var(--text-dim);
}

.book-table tbody tr {
  border-bottom: 1px solid var(--line);
}

.book-table tbody td {
  padding: 10px 12px;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.book-row {
  cursor: pointer;
  transition: background 120ms;
}
.book-row:hover { background: var(--surface-alt); }
.book-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.col-title {
  color: var(--text);
  font-weight: 500;
}

.skeleton-row td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
}
.skeleton-cell {
  display: block;
  height: 0.75rem;
  border-radius: 3px;
  background: var(--surface-alt);
  width: 70%;
  animation: shimmer 1.4s ease-in-out infinite;
}
@keyframes shimmer {
  0%   { opacity: 0.4; }
  50%  { opacity: 0.8; }
  100% { opacity: 0.4; }
}

.col-fav {
  width: 28px;
  text-align: center;
  padding-left: 8px !important;
  padding-right: 0 !important;
}

.fav-btn {
  background: none;
  border: none;
  font-size: 1.05rem;
  color: var(--text-mute);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}
.fav-btn.is-fav { color: var(--fav); }
.fav-btn:hover { color: var(--fav); }

.col-num {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-dim);
}

.col-variants { white-space: nowrap; }

.variant-btn {
  background: transparent;
  border: 1px solid var(--line);
  border-radius: 3px;
  color: var(--text-dim);
  font-size: var(--fs-xs);
  padding: 2px 6px;
  cursor: pointer;
  white-space: nowrap;
  font-family: var(--font-mono);
}
.variant-btn:hover {
  background: var(--surface-alt);
  color: var(--text);
  border-color: var(--line-hard);
}

.variant-row { background: var(--surface-alt); }
.variant-title {
  padding-left: 1.5rem !important;
  font-size: var(--fs-sm);
  color: var(--text-dim) !important;
  font-weight: normal !important;
}

.type-badge {
  display: inline-block;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-dim);
  border: 1px solid var(--line);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  background: transparent;
}

/* ── Cards ── */
.book-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.book-card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 16px;
  text-decoration: none;
  color: inherit;
  display: block;
  transition: border-color 120ms, box-shadow 120ms;
}
.book-card:hover {
  border-color: var(--line-hard);
  box-shadow: var(--shadow-2);
}

.card-fav-btn {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 1.15rem;
}

.card-meta-row {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}

.card-title {
  font-family: var(--font-sans);
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
  letter-spacing: -0.005em;
}

.card-desc {
  font-size: var(--fs-sm);
  color: var(--text-dim);
  line-height: 1.5;
  margin-bottom: 10px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}

.card-footer {
  display: flex;
  gap: 10px;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
}
.page-count, .series-name { color: var(--text-mute); }

/* ── Pagination ── */
.pagination {
  display: flex;
  gap: 4px;
  justify-content: center;
  margin: 24px 0 32px;
  padding: 0 20px;
}

.pagination .btn-secondary {
  font-size: var(--fs-sm);
  padding: 4px 10px;
}

.pagination .active {
  background: var(--text);
  color: var(--surface);
  border-color: var(--text);
}

@media (max-width: 900px) {
  .browse-layout {
    flex-direction: column;
  }
  .rail {
    width: 100%;
    min-width: 0;
    border-right: none;
    border-bottom: 1px solid var(--line);
  }
}
</style>
