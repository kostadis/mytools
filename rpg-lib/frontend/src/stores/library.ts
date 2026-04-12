import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const API = '/api/library'

export interface BookSummary {
  id: number
  display_title: string | null
  filename: string
  publisher: string | null
  collection: string | null
  game_system: string | null
  product_type: string | null
  tags: string[] | null
  series: string | null
  source: string | null
  page_count: number | null
  has_bookmarks: boolean
  description: string | null
  min_level: number | null
  max_level: number | null
  is_favorite: boolean
  variant_count: number
  variant_ids: number[]
}

export interface Bookmark {
  level: number
  title: string
  page_number: number | null
}

export interface BookDetail extends BookSummary {
  filepath: string
  relative_path: string
  pdf_title: string | null
  pdf_author: string | null
  pdf_creator: string | null
  first_page_text: string | null
  is_old_version: boolean
  version_generation: number | null
  product_id: string | null
  product_version: string | null
  date_indexed: string | null
  date_enriched: string | null
  bookmarks: Bookmark[]
}

export interface FilterValue {
  value: string
  count: number
}

export interface Filters {
  game_system: FilterValue[]
  product_type: FilterValue[]
  publisher: FilterValue[]
  series: FilterValue[]
  source: FilterValue[]
  tags: FilterValue[]
}

export interface FacetsResponse {
  total: number
  series: FilterValue[]
  publisher: FilterValue[]
  game_system: FilterValue[]
  tag: FilterValue[]
}

export type GroupByMode = 'books' | 'series' | 'publisher' | 'game_system' | 'tag'

export interface NlqQueryParsed {
  game_system: string | null
  product_type: string | null
  tags: string[]
  keywords: string
  level_min: number | null
  level_max: number | null
}

export interface NlqResponse {
  query_parsed: NlqQueryParsed
  results: BookSummary[]
  total: number
}

export interface TopicStats {
  total: number
  enriched: number
  by_product_type: { value: string; count: number }[]
  top_publishers: { value: string; count: number }[]
  top_tags: { value: string; count: number }[]
  top_series: { value: string; count: number }[]
  top_game_systems: { value: string; count: number }[]
}

export interface TopicResponse {
  topic_type: string
  topic_name: string
  stats: TopicStats
  books: BookSummary[]
}

export interface GraphNode {
  id: number
  label: string
  group: string | null
}

export interface GraphEdge {
  source: number
  target: number
  score: number
}

export interface GraphResponse {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export const useLibraryStore = defineStore('library', () => {
  // State — three separate search fields
  const queryAll = ref('')
  const queryName = ref('')
  const activeFilters = ref<Record<string, string>>({})
  const excludeTags = ref<string[]>([])
  const results = ref<BookSummary[]>([])
  const total = ref(0)
  const page = ref(1)
  const perPage = ref(200)
  const totalPages = ref(0)
  const loading = ref(false)
  const filters = ref<Filters | null>(null)
  const viewMode = ref<'cards' | 'table'>('table')
  const sortField = ref<string | null>(null)
  const sortDir = ref<'asc' | 'desc'>('asc')
  const includeOld = ref(false)
  const includeDrafts = ref(false)
  const includeDuplicates = ref(false)
  const expandedGroups = ref<Set<string>>(new Set())
  const groupVariants = ref<Map<string, BookSummary[]>>(new Map())
  const charLevel = ref<number | null>(null)
  const searchError = ref<string>('')
  const nlqApplied = ref<NlqQueryParsed | null>(null)
  const favoritesOnly = ref(false)

  // Group-by state: when not 'books', the results area shows aggregations of
  // the current search instead of book rows.
  const groupBy = ref<GroupByMode>('books')
  const facets = ref<FacetsResponse | null>(null)
  const facetsLoading = ref(false)

  const title = computed(() => {
    return (book: BookSummary) => book.display_title || book.filename
  })

  /** Build the query-param subset shared by /search and /search/facets. */
  function buildSearchParams(): URLSearchParams {
    const params = new URLSearchParams()
    if (queryAll.value) params.set('q', queryAll.value)
    if (queryName.value) params.set('q_name', queryName.value)
    if (includeOld.value) params.set('include_old', 'true')
    if (includeDrafts.value) params.set('include_drafts', 'true')
    if (includeDuplicates.value) params.set('include_duplicates', 'true')
    for (const [key, val] of Object.entries(activeFilters.value)) {
      if (val) params.set(key, val)
    }
    if (charLevel.value !== null) params.set('char_level', String(charLevel.value))
    if (favoritesOnly.value) params.set('favorites_only', 'true')
    if (excludeTags.value.length) params.set('exclude_tags', excludeTags.value.join(','))
    return params
  }

  async function search() {
    loading.value = true
    searchError.value = ''
    try {
      const params = buildSearchParams()
      params.set('page', String(page.value))
      params.set('per_page', String(perPage.value))
      if (sortField.value) {
        params.set('sort', sortField.value)
        params.set('sort_dir', sortDir.value)
      }

      const res = await fetch(`${API}/search?${params}`)
      if (!res.ok) {
        let msg = `Server error ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) msg = body.detail
        } catch {}
        throw new Error(msg)
      }
      const data = await res.json()
      results.value = data.results
      total.value = data.total
      totalPages.value = data.total_pages
    } catch (e) {
      if (e instanceof TypeError) {
        searchError.value = 'Network error — cannot reach the server'
      } else if (e instanceof Error) {
        searchError.value = e.message
      } else {
        searchError.value = 'Search failed'
      }
    } finally {
      loading.value = false
    }

    // Keep facets in sync when the user is in a group-by view, so that
    // changing filters / queries updates the dimension grid too.
    if (groupBy.value !== 'books') {
      await fetchFacets()
    }
  }

  async function fetchFacets() {
    facetsLoading.value = true
    try {
      const params = buildSearchParams()
      const res = await fetch(`${API}/search/facets?${params}`)
      if (!res.ok) {
        let msg = `Server error ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) msg = body.detail
        } catch {}
        throw new Error(msg)
      }
      facets.value = await res.json()
    } catch (e) {
      if (e instanceof TypeError) {
        searchError.value = 'Network error — cannot reach the server'
      } else if (e instanceof Error) {
        searchError.value = e.message
      } else {
        searchError.value = 'Facets fetch failed'
      }
    } finally {
      facetsLoading.value = false
    }
  }

  async function setGroupBy(mode: GroupByMode) {
    if (groupBy.value === mode) return

    // When switching to a non-books mode, clear any existing filter on that
    // same dimension. Otherwise the facet grid would show only the filtered
    // value (e.g. "Publisher facet with publisher=Chaosium set" returns just
    // Chaosium, count=N) which is useless as a browse tool and leaves the
    // user with no way to back out of a previous drill-in.
    let filterChanged = false
    if (mode !== 'books') {
      const filterKey = mode === 'tag' ? 'tags' : mode
      if (activeFilters.value[filterKey]) {
        delete activeFilters.value[filterKey]
        filterChanged = true
      }
    }

    groupBy.value = mode

    if (mode === 'books') {
      return
    }

    // If we cleared a filter, the books total needs to reflect it too, so
    // re-run the full search (which also refreshes facets). Otherwise just
    // fetch facets if we don't have them yet.
    if (filterChanged) {
      page.value = 1
      await search()
    } else if (!facets.value) {
      await fetchFacets()
    }
  }

  /**
   * Drill-in: when a user clicks a facet row in a group-by view, apply the
   * value as a filter on the underlying search and switch back to the
   * Books view so they see the narrowed result list.
   */
  async function drillInFacet(dimension: GroupByMode, value: string) {
    if (dimension === 'books') return
    // The store's filter key for tags is plural; everything else matches.
    const filterKey = dimension === 'tag' ? 'tags' : dimension
    activeFilters.value[filterKey] = value
    page.value = 1
    groupBy.value = 'books'
    await search()
  }

  async function toggleFavorite(bookId: number) {
    // Find the book in results (or detail) to determine current state
    const book = results.value.find(b => b.id === bookId)
    // Also check expanded variant groups
    let variantBook: BookSummary | undefined
    if (!book) {
      for (const variants of groupVariants.value.values()) {
        variantBook = variants.find(b => b.id === bookId)
        if (variantBook) break
      }
    }
    const target = book || variantBook
    const isFav = target?.is_favorite ?? false
    const method = isFav ? 'DELETE' : 'POST'

    try {
      const res = await fetch(`${API}/book/${bookId}/favorite`, { method })
      if (!res.ok) return
      const newState = !isFav
      // Update in-place in results
      for (const r of results.value) {
        if (r.id === bookId) r.is_favorite = newState
      }
      // Update in variant groups
      for (const variants of groupVariants.value.values()) {
        for (const v of variants) {
          if (v.id === bookId) v.is_favorite = newState
        }
      }
    } catch {
      // Silently fail — next search will re-sync
    }
  }

  function setFavoritesOnly(val: boolean) {
    favoritesOnly.value = val
    page.value = 1
    search()
  }

  function toggleSort(field: string) {
    if (sortField.value === field) {
      sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortDir.value = 'asc'
    }
    page.value = 1
    search()
  }

  function toggleIncludeOld() {
    includeOld.value = !includeOld.value
    page.value = 1
    search()
  }

  function toggleIncludeDrafts() {
    includeDrafts.value = !includeDrafts.value
    page.value = 1
    search()
  }

  function toggleIncludeDuplicates() {
    includeDuplicates.value = !includeDuplicates.value
    page.value = 1
    search()
  }

  async function loadFilters() {
    const res = await fetch(`${API}/filters`)
    filters.value = await res.json()
  }

  async function getBook(id: number): Promise<BookDetail> {
    const res = await fetch(`${API}/book/${id}`)
    if (!res.ok) throw new Error('Book not found')
    return await res.json()
  }

  async function openInApp(id: number) {
    const res = await fetch(`${API}/book/${id}/open`, { method: 'POST' })
    if (!res.ok) {
      const err = await res.json()
      throw new Error(err.detail || 'Failed to open PDF')
    }
  }

  function previewUrl(id: number, page?: number): string {
    const base = `${API}/book/${id}/pdf`
    return page ? `${base}#page=${page}` : base
  }

  function setFilter(key: string, value: string) {
    if (value) {
      activeFilters.value[key] = value
    } else {
      delete activeFilters.value[key]
    }
    page.value = 1
    search()
  }

  function setQuery(all: string, name: string) {
    queryAll.value = all
    queryName.value = name
    page.value = 1
    search()
  }

  function setCharLevel(level: number | null) {
    charLevel.value = level
    page.value = 1
    search()
  }

  function toggleExcludeTag(tag: string) {
    const idx = excludeTags.value.indexOf(tag)
    if (idx === -1) {
      excludeTags.value = [...excludeTags.value, tag]
    } else {
      excludeTags.value = excludeTags.value.filter(t => t !== tag)
    }
    page.value = 1
    search()
  }

  function clearFilters() {
    activeFilters.value = {}
    excludeTags.value = []
    queryAll.value = ''
    queryName.value = ''
    charLevel.value = null
    nlqApplied.value = null
    favoritesOnly.value = false
    page.value = 1
    search()
  }

  function setPage(p: number) {
    page.value = p
    search()
  }

  async function toggleGroup(variantIds: number[]) {
    const key = variantIds.join(',')
    if (expandedGroups.value.has(key)) {
      expandedGroups.value.delete(key)
      // force reactivity
      expandedGroups.value = new Set(expandedGroups.value)
    } else {
      if (!groupVariants.value.has(key)) {
        const res = await fetch(`${API}/books?ids=${key}`)
        const data: BookSummary[] = await res.json()
        groupVariants.value.set(key, data)
        groupVariants.value = new Map(groupVariants.value)
      }
      expandedGroups.value.add(key)
      expandedGroups.value = new Set(expandedGroups.value)
    }
  }

  function isExpanded(variantIds: number[]): boolean {
    return expandedGroups.value.has(variantIds.join(','))
  }

  function getVariants(variantIds: number[]): BookSummary[] {
    return groupVariants.value.get(variantIds.join(',')) ?? []
  }

  // ── Wiki / NLQ actions ──────────────────────────────────────────────────────

  async function nlqSearch(query: string): Promise<NlqResponse> {
    const res = await fetch(`${API}/nlq`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    })
    if (!res.ok) throw new Error('NLQ search failed')
    return await res.json()
  }

  /**
   * Parse a free-text NLQ query and apply the parsed filters as the main search state.
   * Replaces any current filters / queryAll / charLevel. Results appear in the main table.
   *
   * Lossy conversions:
   *  - NLQ may return multiple tags; the UI tag filter is single-select, so only the first
   *    is applied. All parsed tags are still shown in the nlqApplied banner so the user
   *    knows what NLQ understood.
   *  - NLQ returns level_min/level_max; the UI has a single charLevel — we use level_min.
   */
  async function applyNlq(query: string) {
    searchError.value = ''
    loading.value = true
    try {
      const res = await nlqSearch(query)
      const parsed = res.query_parsed
      nlqApplied.value = parsed

      // Reset manual state (mutate keys rather than replace the object so reactive
      // :value bindings on sidebar selects pick up the change)
      for (const key of Object.keys(activeFilters.value)) {
        delete activeFilters.value[key]
      }
      queryName.value = ''

      // Map NLQ output into existing filter state
      queryAll.value = parsed.keywords || ''
      if (parsed.game_system) activeFilters.value.game_system = parsed.game_system
      if (parsed.product_type) activeFilters.value.product_type = parsed.product_type
      if (parsed.tags.length > 0) activeFilters.value.tags = parsed.tags[0]
      charLevel.value = parsed.level_min ?? null

      page.value = 1
      await search()
    } catch (e) {
      if (e instanceof TypeError) {
        searchError.value = 'Network error — cannot reach the server'
      } else if (e instanceof Error) {
        searchError.value = e.message
      } else {
        searchError.value = 'NLQ search failed'
      }
    } finally {
      loading.value = false
    }
  }

  function clearNlq() {
    nlqApplied.value = null
  }

  function setViewMode(mode: 'cards' | 'table') {
    viewMode.value = mode
  }

  async function getTopic(type: string, name: string): Promise<TopicResponse> {
    const res = await fetch(`${API}/topic/${encodeURIComponent(type)}/${encodeURIComponent(name)}`)
    if (!res.ok) throw new Error('Topic not found')
    return await res.json()
  }

  async function getRelatedBooks(id: number): Promise<BookSummary[]> {
    const res = await fetch(`${API}/book/${id}/related`)
    if (!res.ok) return []
    return await res.json()
  }

  async function getGraph(
    minScore: number = 0.25,
    limit: number = 300,
    gameSystem?: string,
  ): Promise<GraphResponse> {
    const params = new URLSearchParams({ min_score: String(minScore), limit: String(limit) })
    if (gameSystem) params.set('game_system', gameSystem)
    const res = await fetch(`${API}/graph?${params}`)
    if (!res.ok) throw new Error('Graph fetch failed')
    return await res.json()
  }

  return {
    activeFilters, results, total, page, perPage, totalPages, loading, searchError, filters,
    viewMode, queryAll, queryName, sortField, sortDir, includeOld, includeDrafts, includeDuplicates,
    charLevel, nlqApplied, favoritesOnly, excludeTags,
    groupBy, facets, facetsLoading,
    title, search, loadFilters, getBook, openInApp, previewUrl,
    setQuery, setFilter, clearFilters, setPage, toggleSort, setCharLevel, setViewMode,
    toggleIncludeOld, toggleIncludeDrafts, toggleIncludeDuplicates,
    toggleFavorite, setFavoritesOnly, toggleExcludeTag,
    toggleGroup, isExpanded, getVariants,
    fetchFacets, setGroupBy, drillInFacet,
    nlqSearch, applyNlq, clearNlq, getTopic, getRelatedBooks, getGraph,
  }
})
