<script setup lang="ts">
</script>

<template>
  <div id="app">
    <header class="app-header">
      <router-link to="/" class="app-title">RPG Library</router-link>
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
}

.app-title {
  color: #e0e0e0;
  text-decoration: none;
  font-size: 1.4rem;
  font-weight: 700;
}
</style>
