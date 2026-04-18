<script setup lang="ts">
defineProps<{
  title: string
  items: { value: string; count: number }[]
  active?: string
}>()

defineEmits<{
  pick: [value: string]
  add: []
}>()
</script>

<template>
  <section class="facet">
    <div class="facet-head">
      <span>{{ title }}</span>
      <button
        type="button"
        class="facet-add"
        :aria-label="`Add ${title} filter`"
        @click="$emit('add')"
      >+</button>
    </div>
    <ul class="facet-list">
      <li
        v-for="it in items"
        :key="it.value"
        :class="{ 'is-active': it.value === active }"
        tabindex="0"
        role="button"
        @click="$emit('pick', it.value === active ? '' : it.value)"
        @keyup.enter="$emit('pick', it.value === active ? '' : it.value)"
      >
        <span class="facet-val">{{ it.value }}</span>
        <span class="facet-count">{{ it.count.toLocaleString() }}</span>
      </li>
    </ul>
    <slot name="footer" />
  </section>
</template>

<style scoped>
.facet { margin-bottom: 18px; }

.facet-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  margin-bottom: 6px;
}

.facet-add {
  background: transparent;
  border: none;
  color: var(--text-mute);
  font-size: 14px;
  line-height: 1;
  padding: 0 4px;
  cursor: pointer;
  border-radius: 3px;
}
.facet-add:hover {
  color: var(--text);
  background: var(--surface-alt);
}

.facet-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.facet-list li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 12.5px;
  cursor: pointer;
}

.facet-list li:hover { background: var(--surface-alt); }

.facet-list li.is-active {
  background: var(--accent-bg);
  font-weight: 500;
}

.facet-val {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 8px;
}

.facet-count {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
  flex-shrink: 0;
  margin-left: 8px;
}
</style>
