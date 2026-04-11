<script setup lang="ts">
</script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="app-title">RPG Library</router-link>
      <nav class="app-nav">
        <router-link to="/" class="nav-link">Search</router-link>
        <span class="nav-group-label">Browse:</span>
        <router-link to="/browse/series" class="nav-link">Series</router-link>
        <router-link to="/browse/publisher" class="nav-link">Publishers</router-link>
        <router-link to="/browse/game_system" class="nav-link">Systems</router-link>
        <router-link to="/browse/tag" class="nav-link">Tags</router-link>
        <router-link to="/graph" class="nav-link">Graph</router-link>
      </nav>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-header {
  background: #1a1a2e;
  color: #e0e0e0;
  padding: 0.75rem 1.5rem;
  border-bottom: 2px solid #e94560;
  display: flex;
  align-items: center;
  gap: 2rem;
}

.app-title {
  color: #e0e0e0;
  text-decoration: none;
  font-size: 1.4rem;
  font-weight: 700;
}

.app-nav {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.nav-group-label {
  color: #6a6a78;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-left: 0.25rem;
  margin-right: -0.25rem;
}

.nav-link {
  color: #a0a0b0;
  text-decoration: none;
  font-size: 0.9rem;
  transition: color 0.15s;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #e94560;
}
</style>
