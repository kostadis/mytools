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

  function previewUrl(id: number): string {
    return `${API}/book/${id}/pdf`
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

  function clearFilters() {
    activeFilters.value = {}
    queryAll.value = ''
    queryName.value = ''
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

  return {
    activeFilters, results, total, page, perPage, totalPages, loading, filters,
    viewMode, queryAll, queryName, sortField, sortDir, includeOld, includeDrafts, includeDuplicates,
    title, search, loadFilters, getBook, openInApp, previewUrl,
    setQuery, setFilter, clearFilters, setPage, toggleSort,
    toggleIncludeOld, toggleIncludeDrafts, toggleIncludeDuplicates,
    toggleGroup, isExpanded, getVariants,
  }
})
