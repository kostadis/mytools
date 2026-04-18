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
    <div class="topic-header">
      <button class="btn-secondary back-btn" @click="router.back()">← Back</button>
      <div class="topic-eyebrow">{{ TYPE_LABELS[props.type] || props.type }}</div>
      <h1>{{ props.name }}</h1>
    </div>

    <div v-if="loading" class="status-msg">Loading…</div>
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

      <div class="breakdown-row">
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
              <div class="bar-fill" :style="{ width: (item.count / maxCount(topic.stats.top_publishers) * 100) + '%' }"></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

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
              <div class="bar-fill" :style="{ width: (item.count / maxCount(topic.stats.top_game_systems) * 100) + '%' }"></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

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
              <div class="bar-fill" :style="{ width: (item.count / maxCount(topic.stats.top_series) * 100) + '%' }"></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </router-link>
        </div>

        <div class="breakdown-panel" v-if="topic.stats.top_tags.length">
          <h3>Top Tags</h3>
          <div class="tag-cloud">
            <router-link
              v-for="item in topic.stats.top_tags"
              :key="item.value"
              class="tag tag-clickable"
              :to="{ name: 'topic', params: { type: 'tag', name: item.value } }"
            >{{ item.value }} <span class="tag-count">{{ item.count }}</span></router-link>
          </div>
        </div>
      </div>

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
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px 32px;
}

.back-btn { margin-bottom: 12px; }

.topic-eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-mute);
  margin-bottom: 4px;
}

h1 {
  font-family: var(--font-serif);
  font-size: var(--fs-2xl);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text);
  margin: 0 0 16px;
}

.status-msg {
  text-align: center;
  padding: 3rem;
  color: var(--text-mute);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
}
.status-msg.error { color: var(--danger); }

/* Stat bar */
.stat-bar {
  display: flex;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  overflow: hidden;
  margin-bottom: 20px;
  background: var(--surface);
}

.stat-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  border-right: 1px solid var(--line);
}
.stat-item:last-child { border-right: none; }

.stat-value {
  font-size: 22px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text);
}

.stat-label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-top: 4px;
  text-align: center;
}

/* Breakdown panels */
.breakdown-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}

.breakdown-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
}

.breakdown-panel h3 {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  margin-bottom: 10px;
  font-weight: 400;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  font-size: var(--fs-sm);
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
  height: 5px;
  background: var(--surface-alt);
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
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
  width: 32px;
  text-align: right;
  flex-shrink: 0;
}

/* Tag cloud */
.tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.tag-clickable { cursor: pointer; }
.tag-count {
  font-size: 10px;
  color: var(--text-mute);
}

/* Book table */
.section-heading h2 {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  margin-bottom: 10px;
  font-weight: 400;
}

.book-table-wrapper { overflow-x: auto; }

.book-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-base);
}

.book-table th {
  text-align: left;
  padding: 6px 12px;
  border-bottom: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  font-weight: 400;
  white-space: nowrap;
}

.book-row { cursor: pointer; transition: background 120ms; }
.book-row:hover { background: var(--surface-alt); }

.book-row td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  color: var(--text);
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.col-title { font-weight: 500; }
.col-num {
  text-align: right;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-dim);
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
</style>
