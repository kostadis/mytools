<script setup lang="ts">
defineProps<{
  modelValue: boolean
  label: string
  muted?: boolean
}>()

defineEmits<{
  'update:modelValue': [val: boolean]
}>()
</script>

<template>
  <label class="cb" :class="{ 'cb--muted': muted }">
    <input
      type="checkbox"
      :checked="modelValue"
      @change="$emit('update:modelValue', ($event.target as HTMLInputElement).checked)"
    />
    <span>{{ label }}</span>
  </label>
</template>

<style scoped>
.cb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--text);
  cursor: pointer;
}

.cb--muted { color: var(--text-dim); }

.cb input[type="checkbox"] {
  width: auto;
  margin: 0;
  padding: 0;
  cursor: pointer;
}
</style>
