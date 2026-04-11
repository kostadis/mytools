<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type TopicResponse } from '../stores/library'

const props = defineProps<{ type: string; name: string }>()
const router = useRouter()
const store = useLibraryStore()

const topic = ref<TopicResponse | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  topic.value = null
  try {
    topic.value = await store.getTopic(props.type, props.name)
  } catch (e) {
    error.value = 'Topic not found.'
  } finally {
    loading.value = false
  }
}

function goToBook(id: number) {
  router.push({ name: 'book', params: { id } })
}

const enrichedPct = computed(() => {
  if (!topic.value) return 0
  const { total, enriched } = topic.value.stats
  return total > 0 ? Math.round((enriched / total) * 100) : 0
})

const TYPE_LABELS: Record<string, string> = {
  game_system: 'Game System',
  tag: 'Tag',
  series: 'Series',
  publisher: 'Publisher',
}

function maxCount(items: { value: string; count: number }[]): number {
  return items.length ? items[0].count : 1
}

onMounted(load)
watch(() => [props.type, props.name], load)
</script>

<template>
  <div class="topic-page">
    <!-- Header -->
    <div class="topic-header">
      <button class="btn-secondary back-btn" @click="router.back()">← Back</button>
      <div class="topic-title-row">
        <span class="topic-type-badge">{{ TYPE_LABELS[props.type] || props.type }}</span>
        <h1>{{ props.name }}</h1>
      </div>
    </div>

    <div v-if="loading" class="status-msg">Loading...</div>
    <div v-else-if="error" class="status-msg error">{{ error }}</div>

    <div v-else-if="topic">

      <!-- Stat bar -->
      <div class="stat-bar">
        <div class="stat-item">
          <span class="stat-value">{{ topic.stats.total.toLocaleString() }}</span>
          <span class="stat-label">books</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ topic.stats.enriched.toLocaleString() }}</span>
          <span class="stat-label">enriched ({{ enrichedPct }}%)</span>
        </div>
        <div class="stat-item" v-for="pt in topic.stats.by_product_type.slice(0, 4)" :key="pt.value">
          <span class="stat-value">{{ pt.count.toLocaleString() }}</span>
          <span class="stat-label">{{ pt.value }}</span>
        </div>
      </div>

      <!-- Breakdown panels -->
      <div class="breakdown-row">

        <!-- Top Publishers -->
        <div class="breakdown-panel" v-if="topic.stats.top_publishers.length">
          <h3>Top Publishers</h3>
          <router-link
            v-for="item in topic.stats.top_publishers.slice(0, 10)"
            :key="item.value"
            class="bar-row"
            :to="{ name: 'topic', params: { type: 'publisher', name: item.value } }"
          >
            <span class="bar-label">{{ item.value }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ width: (item.count / maxCount(topic.stats.top_publishers) * 100) + '%' }"
              ></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

        <!-- Top Game Systems -->
        <div class="breakdown-panel" v-if="topic.stats.top_game_systems.length">
          <h3>Game Systems</h3>
          <router-link
            v-for="item in topic.stats.top_game_systems.slice(0, 10)"
            :key="item.value"
            class="bar-row"
            :to="{ name: 'topic', params: { type: 'game_system', name: item.value } }"
          >
            <span class="bar-label">{{ item.value }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ width: (item.count / maxCount(topic.stats.top_game_systems) * 100) + '%' }"
              ></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

        <!-- Top Series -->
        <div class="breakdown-panel" v-if="topic.stats.top_series.length">
          <h3>Series</h3>
          <router-link
            v-for="item in topic.stats.top_series.slice(0, 10)"
            :key="item.value"
            class="bar-row"
            :to="{ name: 'topic', params: { type: 'series', name: item.value } }"
          >
            <span class="bar-label">{{ item.value }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ width: (item.count / maxCount(topic.stats.top_series) * 100) + '%' }"
              ></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

        <!-- Top Tags -->
        <div class="breakdown-panel" v-if="topic.stats.top_tags.length">
          <h3>Top Tags</h3>
          <div class="tag-cloud">
            <router-link
              v-for="item in topic.stats.top_tags"
              :key="item.value"
              class="tag tag-clickable"
              :style="{ fontSize: (0.7 + (item.count / maxCount(topic.stats.top_tags)) * 0.45) + 'rem' }"
              :to="{ name: 'topic', params: { type: 'tag', name: item.value } }"
            >{{ item.value }} <span class="tag-count">{{ item.count }}</span></router-link>
          </div>
        </div>

      </div>

      <!-- Book list -->
      <div class="section-heading">
        <h2>All Books ({{ topic.books.length.toLocaleString() }})</h2>
      </div>
      <div class="book-table-wrapper">
        <table class="book-table">
          <thead>
            <tr>
              <th>Title</th>
              <th v-if="props.type !== 'publisher'">Publisher</th>
              <th v-if="props.type !== 'game_system'">System</th>
              <th>Type</th>
              <th v-if="props.type !== 'series'">Series</th>
              <th class="col-num">Pages</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="book in topic.books"
              :key="book.id"
              class="book-row"
              tabindex="0"
              role="link"
              :aria-label="`Open ${book.display_title || book.filename}`"
              @click="goToBook(book.id)"
              @keyup.enter="goToBook(book.id)"
              @keyup.space.prevent="goToBook(book.id)"
            >
              <td class="col-title">{{ book.display_title || book.filename }}</td>
              <td v-if="props.type !== 'publisher'">{{ book.publisher }}</td>
              <td v-if="props.type !== 'game_system'">{{ book.game_system }}</td>
              <td><span v-if="book.product_type" class="type-badge">{{ book.product_type }}</span></td>
              <td v-if="props.type !== 'series'">{{ book.series }}</td>
              <td class="col-num">{{ book.page_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.topic-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem;
}

.back-btn { margin-bottom: 0.75rem; }

.topic-title-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.topic-type-badge {
  background: var(--accent);
  color: white;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

h1 {
  font-size: 1.6rem;
  color: var(--text-bright);
  margin: 0;
}

.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-dim);
}
.status-msg.error { color: var(--accent); }

/* Stat bar */
.stat-bar {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 1.25rem;
}

.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.75rem 0.5rem;
  border-right: 1px solid var(--border);
  background: var(--bg-card);
}
.stat-item:last-child { border-right: none; }

.stat-value {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--text-bright);
}

.stat-label {
  font-size: 0.7rem;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 0.2rem;
  text-align: center;
}

/* Breakdown panels */
.breakdown-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.breakdown-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.9rem 1rem;
}

.breakdown-panel h3 {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  margin-bottom: 0.75rem;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
  cursor: pointer;
  font-size: 0.8rem;
  color: inherit;
  text-decoration: none;
}
.bar-row:hover .bar-label { color: var(--accent); }

.bar-label {
  width: 130px;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text);
}

.bar-track {
  flex: 1;
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.3s;
}

.bar-count {
  font-size: 0.72rem;
  color: var(--text-dim);
  width: 32px;
  text-align: right;
  flex-shrink: 0;
}

/* Tag cloud */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: baseline;
}

.tag-clickable {
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.tag-clickable:hover {
  background: var(--accent);
  color: white;
}

.tag-count {
  font-size: 0.65em;
  opacity: 0.7;
}

/* Book table */
.section-heading h2 {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-dim);
  margin-bottom: 0.5rem;
}

.book-table-wrapper {
  overflow-x: auto;
}

.book-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.book-table th {
  text-align: left;
  padding: 0.4rem 0.6rem;
  border-bottom: 2px solid var(--border);
  color: var(--text-dim);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.book-row {
  cursor: pointer;
  transition: background 0.12s;
}
.book-row:hover { background: var(--bg-card); }

.book-row td {
  padding: 0.35rem 0.6rem;
  border-bottom: 1px solid var(--border);
  color: var(--text);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-title {
  color: var(--text-bright) !important;
  font-weight: 500;
}

.col-num { text-align: right; }

.type-badge {
  background: var(--accent);
  color: white;
  padding: 0.1rem 0.4rem;
  border-radius: 3px;
  font-size: 0.68rem;
  text-transform: uppercase;
}
</style>
