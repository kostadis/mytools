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

export interface NlqQueryParsed {
  game_system: string | null
  product_type: string | null
  tags: string[]
  keywords: string
  char_level: number | null
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

  const title = computed(() => {
    return (book: BookSummary) => book.display_title || book.filename
  })

  async function search() {
    loading.value = true
    try {
      const params = new URLSearchParams()
      if (queryAll.value) params.set('q', queryAll.value)
      if (queryName.value) params.set('q_name', queryName.value)

      params.set('page', String(page.value))
      params.set('per_page', String(perPage.value))
      if (sortField.value) {
        params.set('sort', sortField.value)
        params.set('sort_dir', sortDir.value)
      }
      if (includeOld.value) params.set('include_old', 'true')
      if (includeDrafts.value) params.set('include_drafts', 'true')
      if (includeDuplicates.value) params.set('include_duplicates', 'true')

      for (const [key, val] of Object.entries(activeFilters.value)) {
        if (val) params.set(key, val)
      }
      if (charLevel.value !== null) params.set('char_level', String(charLevel.value))

      const res = await fetch(`${API}/search?${params}`)
      const data = await res.json()
      results.value = data.results
      total.value = data.total
      totalPages.value = data.total_pages
    } finally {
      loading.value = false
    }
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

  function clearFilters() {
    activeFilters.value = {}
    queryAll.value = ''
    queryName.value = ''
    charLevel.value = null
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
    activeFilters, results, total, page, perPage, totalPages, loading, filters,
    viewMode, queryAll, queryName, sortField, sortDir, includeOld, includeDrafts, includeDuplicates,
    charLevel,
    title, search, loadFilters, getBook, openInApp, previewUrl,
    setQuery, setFilter, clearFilters, setPage, toggleSort, setCharLevel,
    toggleIncludeOld, toggleIncludeDrafts, toggleIncludeDuplicates,
    toggleGroup, isExpanded, getVariants,
    nlqSearch, getTopic, getRelatedBooks, getGraph,
  }
})
