<script setup lang="ts">
defineProps<{
  items: { value: string; count: number }[]
  ariaPrefix?: string
}>()

defineEmits<{
  select: [value: string]
}>()
</script>

<template>
  <div class="dimension-grid">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      class="dimension-row"
      :aria-label="`${ariaPrefix ?? 'View'} ${item.value} (${item.count} books)`"
      @click="$emit('select', item.value)"
    >
      <span class="dimension-name">{{ item.value }}</span>
      <span class="dimension-count">{{ item.count.toLocaleString() }}</span>
    </button>
  </div>
</template>

<style scoped>
.dimension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.5rem;
}

.dimension-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.6rem 0.85rem;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  text-align: left;
  color: var(--text);
  font-size: 0.85rem;
  font-family: inherit;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.dimension-row:hover {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.dimension-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.dimension-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.dimension-count {
  flex-shrink: 0;
  font-size: 0.78rem;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}

.dimension-row:hover .dimension-count {
  color: rgba(255, 255, 255, 0.85);
}
</style>
