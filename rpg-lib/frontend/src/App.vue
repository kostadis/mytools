<script setup lang="ts">
</script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="app-title">RPG Library</router-link>
      <nav class="app-nav">
        <router-link to="/" class="nav-link">Browse</router-link>
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
  gap: 1.25rem;
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
