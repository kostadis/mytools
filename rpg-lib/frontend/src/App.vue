<script setup lang="ts">
import { onMounted } from 'vue'
import { useLibraryStore } from './stores/library'

const store = useLibraryStore()

onMounted(async () => {
  if (!store.filters) await store.loadFilters()
})
</script>

<template>
  <div id="app">
    <header class="topbar">
      <router-link to="/" class="brand">
        <span class="brand-mark"></span>
        <span class="brand-name">RPG Library</span>
      </router-link>

      <nav class="topnav">
        <router-link to="/">Search</router-link>
        <router-link to="/browse/series">Series</router-link>
        <router-link to="/browse/publisher">Publishers</router-link>
        <router-link to="/browse/game_system">Systems</router-link>
        <router-link to="/browse/tag">Tags</router-link>
        <router-link to="/graph">Graph</router-link>
      </nav>

      <div class="topbar-right">
        <span class="kbd">⌘K</span>
        <span class="stat" v-if="store.totalBooks">{{ store.totalBooks.toLocaleString() }} books</span>
      </div>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.topbar {
  height: 52px;
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}

.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-serif);
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--text);
  text-decoration: none;
  letter-spacing: -0.01em;
}

.brand-mark {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  background: var(--text);
}

.topnav {
  display: flex;
  gap: 2px;
}

.topnav a {
  padding: 6px 10px;
  border-radius: var(--radius);
  font-size: 12.5px;
  color: var(--text-dim);
  text-decoration: none;
}

.topnav a:hover {
  background: var(--surface-alt);
  color: var(--text);
}

.topnav a.router-link-active {
  background: var(--chip-bg);
  color: var(--text);
  font-weight: 500;
}

/* "Search" tab is the root path; only highlight on exact match so it doesn't
   stay lit when the user navigates to /browse/* or /book/*. */
.topnav a[href="/"].router-link-active {
  background: transparent;
  color: var(--text-dim);
}
.topnav a[href="/"].router-link-exact-active {
  background: var(--chip-bg);
  color: var(--text);
  font-weight: 500;
}

.topbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  color: var(--text-mute);
}

.kbd {
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1px 5px;
  background: var(--surface);
}
</style>
