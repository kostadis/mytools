<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useLibraryStore, type BookDetail, type BookSummary, type Bookmark } from '../stores/library'

const route = useRoute()
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
  openStatus.value = 'Opening…'
  try {
    await store.openInApp(book.value.id)
    openStatus.value = 'Opened'
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
      <div class="breadcrumb">
        ←
        <router-link :to="{ name: 'browse' }">Search</router-link>
        <template v-if="book.tags && book.tags.length">
          /
          <router-link :to="{ name: 'topic', params: { type: 'tag', name: book.tags[0] } }">{{ book.tags[0] }}</router-link>
        </template>
        / {{ book.display_title || book.filename }}
      </div>

      <div class="detail-eyebrow">
        <template v-if="book.publisher">{{ book.publisher }}</template>
        <template v-if="book.publisher && book.game_system"> · </template>
        <template v-if="book.game_system">{{ book.game_system }}</template>
      </div>

      <h1 class="detail-title">{{ book.display_title || book.filename }}</h1>

      <div class="detail-meta">
        <span v-if="book.product_type">{{ book.product_type.toLowerCase() }}</span>
        <span v-if="book.product_type && book.page_count">·</span>
        <span v-if="book.page_count">{{ book.page_count }} pages</span>
        <template v-if="book.min_level">
          <span>·</span>
          <span>levels {{ book.min_level === book.max_level ? book.min_level : `${book.min_level}–${book.max_level}` }}</span>
        </template>
        <template v-if="book.is_favorite">
          <span>·</span>
          <span class="is-fav">♥ favorited</span>
        </template>
      </div>

      <!-- Actions -->
      <div class="detail-actions">
        <button class="btn-primary" @click="openInApp">Open PDF</button>
        <button class="btn-secondary" @click="previewPdf">Preview in browser</button>
        <button
          class="btn-secondary fav-toggle"
          :class="{ 'is-fav': book.is_favorite }"
          @click="toggleFav"
        >{{ book.is_favorite ? '♥ Favorited' : '♡ Favorite' }}</button>
        <span v-if="openStatus" class="open-status">{{ openStatus }}</span>
      </div>

      <!-- Description -->
      <div class="detail-description" v-if="book.description">
        {{ book.description }}
      </div>

      <!-- Tags -->
      <div class="detail-section" v-if="book.tags && book.tags.length">
        <div class="detail-section-head">Tags</div>
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
      <div class="detail-section" v-if="book.series">
        <div class="detail-section-head">Series</div>
        <router-link
          class="series-link"
          :to="{ name: 'topic', params: { type: 'series', name: book.series } }"
        >{{ book.series }}</router-link>
      </div>

      <!-- Related Books -->
      <div class="detail-section" v-if="related.length">
        <div class="detail-section-head">Related Books</div>
        <div class="related-grid">
          <router-link
            v-for="r in related"
            :key="r.id"
            class="related-card"
            :to="{ name: 'book', params: { id: r.id } }"
          >
            <div class="related-meta-row" v-if="r.game_system">{{ r.game_system }}</div>
            <div class="related-title">{{ r.display_title || r.filename }}</div>
            <div v-if="r.tags && r.tags.length" class="related-tags">
              <span v-for="tag in r.tags.slice(0, 4)" :key="tag" class="tag tag-sm">{{ tag }}</span>
            </div>
          </router-link>
        </div>
      </div>

      <!-- Bookmarks -->
      <div class="detail-section" v-if="book.bookmarks.length">
        <div class="detail-section-head">Table of Contents ({{ book.bookmarks.length }})</div>
        <div class="toc-list">
          <div
            v-for="(bm, i) in book.bookmarks"
            :key="i"
            class="toc-item"
            :class="{ 'toc-link': bm.page_number }"
            :style="{ paddingLeft: bookmarkIndent(bm) }"
            @click="openAtPage(bm.page_number)"
          >
            <span class="toc-title">{{ bm.title }}</span>
            <span v-if="bm.page_number" class="toc-page">p.{{ bm.page_number }}</span>
          </div>
        </div>
      </div>

      <!-- Metadata -->
      <div class="detail-section">
        <div class="detail-section-head">Metadata</div>
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
  max-width: 780px;
  margin: 0 auto;
  padding: 24px 48px;
}

.error {
  color: var(--danger);
  text-align: center;
  padding: 3rem;
  font-size: 1.2rem;
}

.breadcrumb {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 18px;
}
.breadcrumb a {
  color: var(--text-mute);
  text-decoration: none;
}
.breadcrumb a:hover { color: var(--accent); }

.detail-eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-mute);
  margin-bottom: 6px;
}

.detail-title {
  font-family: var(--font-serif);
  font-size: var(--fs-3xl);
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.15;
  color: var(--text);
  margin: 0 0 12px;
}

.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-dim);
  margin-bottom: 20px;
}
.detail-meta .is-fav { color: var(--fav); }

.detail-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 28px;
}

.fav-toggle.is-fav {
  color: var(--fav);
  border-color: var(--fav);
}

.open-status {
  font-size: var(--fs-sm);
  color: var(--success);
  font-family: var(--font-mono);
}

.detail-description {
  font-family: var(--font-serif);
  font-size: 15.5px;
  line-height: 1.65;
  color: var(--text);
  max-width: 620px;
  margin-bottom: 28px;
}

.detail-section {
  margin-bottom: 28px;
}

.detail-section-head {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-mute);
  margin-bottom: 10px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.series-link {
  color: var(--accent);
  text-decoration: none;
  font-size: var(--fs-md);
}
.series-link:hover { text-decoration: underline; }

/* TOC */
.toc-list {
  max-height: 500px;
  overflow-y: auto;
}
.toc-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 4px 0;
  border-bottom: 1px dotted var(--line);
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text);
}
.toc-link { cursor: pointer; }
.toc-link:hover .toc-title { color: var(--accent); }
.toc-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 8px;
}
.toc-page {
  color: var(--text-mute);
  font-size: 11px;
  flex-shrink: 0;
}

/* Metadata table */
.meta-table {
  width: 100%;
  border-collapse: collapse;
}
.meta-table td {
  padding: 6px 12px;
  border-bottom: 1px solid var(--line);
  font-size: var(--fs-sm);
  color: var(--text);
  vertical-align: top;
}
.meta-table td:first-child {
  color: var(--text-mute);
  width: 130px;
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.path-cell {
  word-break: break-all;
  font-family: var(--font-mono);
  font-size: 11.5px;
}

/* Related books */
.related-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}
.related-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
  text-decoration: none;
  color: inherit;
  display: block;
  transition: border-color 120ms;
}
.related-card:hover {
  border-color: var(--line-hard);
  background: var(--surface-alt);
}

.related-meta-row {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.related-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.related-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.tag-sm {
  font-size: 10px !important;
  padding: 1px 5px !important;
}

@media (max-width: 700px) {
  .detail-page {
    padding: 20px 16px;
  }
}
</style>
