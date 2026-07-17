<script setup lang="ts">
import { useAdventure } from '../../stores/adventure'

const store = useAdventure()
</script>

<template>
  <div class="multi-bar">
    <span class="multi-count">{{ store.selectionCount }} selected</span>
    <button title="Move selected up" @click="store.bulkMove(-1)">↑ Up</button>
    <button title="Move selected down" @click="store.bulkMove(1)">↓ Down</button>
    <button title="Demote all selected (nest into preceding sibling)" @click="store.bulkDemote()">Demote →</button>
    <button title="Promote all selected (move out of parent)" @click="store.bulkPromote()">← Promote</button>
    <button class="btn-warning" title="Dissolve all selected (remove blocks, keep children)" @click="store.bulkDissolve()">Dissolve</button>
    <button class="btn-danger" title="Delete all selected" @click="store.bulkDelete()">Delete</button>
    <span class="sep"></span>
    <button class="flag-btn flag-1e" title="Flag as 1e stat block" @click="store.bulkFlag('1e')">Flag 1e</button>
    <button class="flag-btn flag-review" title="Flag for review" @click="store.bulkFlag('review')">Flag Review</button>
    <button title="Clear all flags from selected" @click="store.bulkClearFlags()">Clear flags</button>
    <span class="flex-spacer"></span>
    <button @click="store.clearSelection()">Clear</button>
  </div>
</template>
