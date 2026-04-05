<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useLibraryStore, type BookDetail, type Bookmark } from '../stores/library'

const route = useRoute()
const router = useRouter()
const store = useLibraryStore()

const book = ref<BookDetail | null>(null)
const error = ref('')
const openStatus = ref('')

onMounted(async () => {
  try {
    book.value = await store.getBook(Number(route.params.id))
  } catch (e) {
    error.value = 'Book not found'
  }
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

function searchByTag(tag: string) {
  store.setFilter('tags', tag)
  router.push({ name: 'browse' })
}

function searchByPublisher() {
  if (!book.value?.publisher) return
  store.setFilter('publisher', book.value.publisher)
  router.push({ name: 'browse' })
}

function searchBySeries() {
  if (!book.value?.series) return
  store.setFilter('series', book.value.series)
  router.push({ name: 'browse' })
}

function bookmarkIndent(bm: Bookmark): string {
  return `${(bm.level - 1) * 1.25}rem`
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
          <span v-if="book.publisher" class="meta-link" @click="searchByPublisher">
            {{ book.publisher }}
          </span>
          <span v-if="book.game_system" class="meta-system">{{ book.game_system }}</span>
          <span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span>
          <span v-if="book.page_count" class="meta-pages">{{ book.page_count }} pages</span>
        </div>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="btn-primary" @click="openInApp">Open in App</button>
        <button class="btn-secondary" @click="previewPdf">Preview in Browser</button>
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
          <span
            v-for="tag in book.tags"
            :key="tag"
            class="tag"
            @click="searchByTag(tag)"
          >{{ tag }}</span>
        </div>
      </div>

      <!-- Series -->
      <div class="section" v-if="book.series">
        <h2>Series</h2>
        <span class="meta-link" @click="searchBySeries">{{ book.series }}</span>
      </div>

      <!-- Bookmarks -->
      <div class="section" v-if="book.bookmarks.length">
        <h2>Table of Contents ({{ book.bookmarks.length }})</h2>
        <div class="bookmark-tree">
          <div
            v-for="(bm, i) in book.bookmarks"
            :key="i"
            class="bookmark-item"
            :style="{ paddingLeft: bookmarkIndent(bm) }"
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
</style>
