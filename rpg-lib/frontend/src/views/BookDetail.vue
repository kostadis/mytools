<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLibraryStore, type BookDetail, type BookSummary, type Bookmark } from '../stores/library'

const route = useRoute()
const router = useRouter()
const store = useLibraryStore()

const book = ref<BookDetail | null>(null)
const error = ref('')
const openStatus = ref('')
const related = ref<BookSummary[]>([])

async function loadBook(id: number) {
  book.value = null
  error.value = ''
  openStatus.value = ''
  related.value = []
  try {
    book.value = await store.getBook(id)
    related.value = await store.getRelatedBooks(id)
  } catch (e) {
    error.value = 'Book not found'
  }
}

onMounted(() => loadBook(Number(route.params.id)))

watch(() => route.params.id, (newId) => {
  if (newId) loadBook(Number(newId))
})

async function openInApp() {
  if (!book.value) return
  openStatus.value = 'Opening...'
  try {
    await store.openInApp(book.value.id)
    openStatus.value = 'Opened!'
    setTimeout(() => { openStatus.value = '' }, 2000)
  } catch (e: any) {
    openStatus.value = `Error: ${e.message}`
  }
}

function previewPdf() {
  if (!book.value) return
  window.open(store.previewUrl(book.value.id), '_blank')
}

async function toggleFav() {
  if (!book.value) return
  await store.toggleFavorite(book.value.id)
  book.value.is_favorite = !book.value.is_favorite
}

function bookmarkIndent(bm: Bookmark): string {
  return `${(bm.level - 1) * 1.25}rem`
}

function openAtPage(page: number | null) {
  if (!book.value || !page) return
  window.open(store.previewUrl(book.value.id, page), '_blank')
}
</script>

<template>
  <div class="detail-page">
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="book" class="detail-layout">
      <!-- Header -->
      <div class="detail-header">
        <button class="btn-secondary back-btn" @click="router.push({ name: 'browse' })">
          &larr; Back
        </button>
        <h1>{{ book.display_title || book.filename }}</h1>
        <div class="header-meta">
          <router-link
            v-if="book.publisher"
            class="meta-link"
            :to="{ name: 'topic', params: { type: 'publisher', name: book.publisher } }"
          >{{ book.publisher }}</router-link>
          <router-link
            v-if="book.game_system"
            class="meta-link"
            :to="{ name: 'topic', params: { type: 'game_system', name: book.game_system } }"
          >{{ book.game_system }}</router-link>
          <span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span>
          <span v-if="book.page_count" class="meta-pages">{{ book.page_count }} pages</span>
          <span v-if="book.min_level" class="meta-pages">
            Levels {{ book.min_level === book.max_level ? book.min_level : `${book.min_level}–${book.max_level}` }}
          </span>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="btn-primary" @click="openInApp">Open in App</button>
        <button class="btn-secondary" @click="previewPdf">Preview in Browser</button>
        <button
          :class="['btn-secondary', 'btn-fav', { 'btn-fav-active': book.is_favorite }]"
          @click="toggleFav"
        >{{ book.is_favorite ? '\u2665 Favorited' : '\u2661 Favorite' }}</button>
        <span v-if="openStatus" class="open-status">{{ openStatus }}</span>
      </div>

      <!-- Description -->
      <div class="section" v-if="book.description">
        <h2>Description</h2>
        <p>{{ book.description }}</p>
      </div>

      <!-- Tags -->
      <div class="section" v-if="book.tags && book.tags.length">
        <h2>Tags</h2>
        <div class="tags-list">
          <router-link
            v-for="tag in book.tags"
            :key="tag"
            class="tag"
            :to="{ name: 'topic', params: { type: 'tag', name: tag } }"
          >{{ tag }}</router-link>
        </div>
      </div>

      <!-- Series -->
      <div class="section" v-if="book.series">
        <h2>Series</h2>
        <router-link
          class="meta-link"
          :to="{ name: 'topic', params: { type: 'series', name: book.series } }"
        >{{ book.series }}</router-link>
      </div>

      <!-- Related Books -->
      <div class="section" v-if="related.length">
        <h2>Related Books</h2>
        <div class="related-scroll">
          <router-link
            v-for="r in related"
            :key="r.id"
            class="related-card"
            :to="{ name: 'book', params: { id: r.id } }"
          >
            <div class="related-title">{{ r.display_title || r.filename }}</div>
            <div class="related-meta">
              <span v-if="r.game_system" class="related-system">{{ r.game_system }}</span>
              <span v-if="r.product_type" class="type-badge">{{ r.product_type }}</span>
            </div>
            <div v-if="r.tags && r.tags.length" class="related-tags">
              <span v-for="tag in r.tags.slice(0, 4)" :key="tag" class="tag tag-sm">{{ tag }}</span>
            </div>
          </router-link>
        </div>
      </div>

      <!-- Bookmarks -->
      <div class="section" v-if="book.bookmarks.length">
        <h2>Table of Contents ({{ book.bookmarks.length }})</h2>
        <div class="bookmark-tree">
          <div
            v-for="(bm, i) in book.bookmarks"
            :key="i"
            class="bookmark-item"
            :class="{ 'bookmark-link': bm.page_number }"
            :style="{ paddingLeft: bookmarkIndent(bm) }"
            @click="openAtPage(bm.page_number)"
          >
            <span class="bm-title">{{ bm.title }}</span>
            <span v-if="bm.page_number" class="bm-page">p.{{ bm.page_number }}</span>
          </div>
        </div>
      </div>

      <!-- Metadata -->
      <div class="section">
        <h2>Metadata</h2>
        <table class="meta-table">
          <tr><td>Filename</td><td>{{ book.filename }}</td></tr>
          <tr v-if="book.pdf_title"><td>PDF Title</td><td>{{ book.pdf_title }}</td></tr>
          <tr v-if="book.pdf_author"><td>PDF Author</td><td>{{ book.pdf_author }}</td></tr>
          <tr v-if="book.collection"><td>Collection</td><td>{{ book.collection }}</td></tr>
          <tr v-if="book.source"><td>Source</td><td>{{ book.source }}</td></tr>
          <tr v-if="book.product_id"><td>Product ID</td><td>{{ book.product_id }}</td></tr>
          <tr v-if="book.product_version"><td>Version</td><td>{{ book.product_version }}</td></tr>
          <tr><td>Path</td><td class="path-cell">{{ book.relative_path }}</td></tr>
          <tr v-if="book.date_indexed"><td>Indexed</td><td>{{ book.date_indexed.slice(0, 10) }}</td></tr>
          <tr v-if="book.date_enriched"><td>Enriched</td><td>{{ book.date_enriched.slice(0, 10) }}</td></tr>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 1.5rem;
}

.error {
  color: var(--accent);
  text-align: center;
  padding: 3rem;
  font-size: 1.2rem;
}

.detail-header {
  margin-bottom: 1rem;
}

.back-btn {
  margin-bottom: 0.75rem;
}

h1 {
  font-size: 1.6rem;
  color: var(--text-bright);
  margin-bottom: 0.5rem;
  line-height: 1.3;
}

h2 {
  font-size: 1rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.5rem;
}

.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  font-size: 0.875rem;
}

.meta-link {
  color: var(--accent);
  cursor: pointer;
}
.meta-link:hover { color: var(--accent-hover); }

.meta-system {
  color: var(--text-dim);
}

.meta-pages {
  color: var(--text-dim);
}

.type-badge {
  background: var(--accent);
  color: white;
  padding: 0.1rem 0.5rem;
  border-radius: 3px;
  font-size: 0.75rem;
  text-transform: uppercase;
}

.actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1.5rem;
}

.btn-fav-active {
  color: #e25555;
  border-color: #e25555;
}

.btn-fav:hover {
  color: #e25555;
  border-color: #e25555;
}

.open-status {
  font-size: 0.875rem;
  color: var(--success);
}

.section {
  margin-bottom: 1.5rem;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.bookmark-tree {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  max-height: 500px;
  overflow-y: auto;
}

.bookmark-item {
  display: flex;
  justify-content: space-between;
  padding: 0.2rem 0;
  font-size: 0.85rem;
}

.bookmark-link {
  cursor: pointer;
}
.bookmark-link:hover .bm-title {
  color: var(--accent);
}

.bm-title {
  color: var(--text);
}

.bm-page {
  color: var(--text-dim);
  font-size: 0.75rem;
  flex-shrink: 0;
  margin-left: 1rem;
}

.meta-table {
  width: 100%;
  border-collapse: collapse;
}

.meta-table td {
  padding: 0.35rem 0.75rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.85rem;
}

.meta-table td:first-child {
  color: var(--text-dim);
  width: 130px;
  white-space: nowrap;
}

.path-cell {
  word-break: break-all;
  font-family: monospace;
  font-size: 0.8rem;
}

.related-scroll {
  display: flex;
  gap: 0.75rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}

.related-card {
  display: block;
  min-width: 180px;
  max-width: 220px;
  flex-shrink: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.6rem;
  cursor: pointer;
  transition: border-color 0.15s;
  color: inherit;
  text-decoration: none;
}

.related-card:hover { border-color: var(--accent); color: inherit; }

.related-title {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-bright);
  margin-bottom: 0.3rem;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.related-meta {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  margin-bottom: 0.3rem;
  font-size: 0.72rem;
}

.related-system { color: var(--text-dim); }

.related-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.tag-sm {
  font-size: 0.65rem !important;
  padding: 0.05rem 0.35rem !important;
}
</style>
