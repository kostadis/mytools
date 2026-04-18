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
  <div class="dir-index">
    <button
      v-for="item in items"
      :key="item.value"
      type="button"
      class="dir-row"
      :aria-label="`${ariaPrefix ?? 'View'} ${item.value} (${item.count} books)`"
      @click="$emit('select', item.value)"
    >
      <span class="dir-name">{{ item.value }}</span>
      <span class="dir-count">{{ item.count.toLocaleString() }}</span>
    </button>
  </div>
</template>

<style scoped>
.dir-index {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  column-gap: 24px;
  max-width: 900px;
}

.dir-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  text-decoration: none;
  color: var(--text);
  font-size: 13.5px;
  background: transparent;
  border-left: none;
  border-right: none;
  border-top: none;
  border-radius: 0;
  text-align: left;
  font-family: inherit;
  cursor: pointer;
}

.dir-row:hover .dir-name {
  color: var(--accent);
}

.dir-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 12px;
  font-weight: 500;
}

.dir-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

@media (max-width: 700px) {
  .dir-index {
    grid-template-columns: 1fr;
  }
}
</style>
