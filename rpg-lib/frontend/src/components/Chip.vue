<script setup lang="ts">
defineProps<{
  label: string
  value: string
  excluded?: boolean
  showInvert?: boolean
}>()

defineEmits<{
  remove: []
  invert: []
}>()
</script>

<template>
  <span class="chip" :class="{ 'chip--excluded': excluded }">
    <span class="chip-key">{{ label }}:</span>
    <span class="chip-value">{{ value }}</span>
    <button
      v-if="showInvert"
      type="button"
      class="chip-x"
      :aria-label="`Exclude ${value}`"
      title="Exclude this filter"
      @click.stop="$emit('invert')"
    >≠</button>
    <button
      type="button"
      class="chip-x"
      :aria-label="`Remove ${label} filter`"
      @click.stop="$emit('remove')"
    >✕</button>
  </span>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--chip-bg);
  color: var(--chip-text);
  font-size: var(--fs-sm);
  line-height: 1.5;
  white-space: nowrap;
}

.chip-key {
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--text-mute);
  text-transform: lowercase;
}

.chip-value {
  font-weight: 500;
}

.chip-x {
  width: 14px;
  height: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-mute);
  font-size: 11px;
  cursor: pointer;
  background: transparent;
  border: none;
  padding: 0;
  border-radius: 3px;
}
.chip-x:hover {
  background: var(--line-hard);
  color: var(--text);
}

.chip--excluded {
  background: #fbeae7;
  color: var(--danger);
}
.chip--excluded .chip-value {
  text-decoration: line-through;
}
</style>
