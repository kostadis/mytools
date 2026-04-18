<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useLibraryStore } from '../stores/library'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const store = useLibraryStore()

const TAG_GROUPS: { label: string; tags: string[] }[] = [
  {
    label: 'Content',
    tags: ['monsters', 'encounters', 'combat', 'traps', 'dragons',
           'spells', 'subclasses', 'feats', 'races', 'classes', 'backgrounds',
           'skills', 'equipment', 'weapons', 'vehicles',
           'npc', 'factions', 'lore', 'worldbuilding', 'treasure',
           'random_tables', 'rules', 'crafting', 'character_creation',
           'names', 'locations', 'undead', 'lair'],
  },
  {
    label: 'Setting',
    tags: ['dungeon', 'wilderness', 'urban', 'naval', 'planar',
           'forgotten_realms', 'greyhawk', 'eberron', 'ravenloft',
           'spelljammer', 'planescape', 'dragonlance',
           'icewind_dale', 'underdark', 'waterdeep'],
  },
  {
    label: 'Format',
    tags: ['maps', 'battlemaps', 'hexcrawl', 'sandbox', 'mega_dungeon',
           'handouts', 'tokens', 'miniatures', 'player_aid',
           'fillable', 'print_and_play', 'cards',
           'one_shot', 'campaign', 'solo_play', 'organized_play'],
  },
  {
    label: 'Genre',
    tags: ['horror', 'sci_fi', 'cyberpunk', 'steampunk', 'historical',
           'mystery', 'dark_fantasy', 'humor'],
  },
  {
    label: 'System',
    tags: ['5e', '5e_2024', '3_5e', '4e', 'ad_d', 'od_d', 'osr',
           'pf1e', 'pf2e', 'dcc', '13th_age', 'shadow_demon_lord',
           'castles_and_crusades', 'zweihander',
           'coc', 'fate', 'gurps', 'savage_worlds',
           'pbta', 'dungeon_world', 'blades',
           'year_zero', 'cypher', 'mothership', 'alien_rpg',
           'dragonbane', 'vtm', '2d20', 'conan', 'iron_kingdoms',
           'tinyd6', 'dune', 'system_neutral'],
  },
]

const TAB_LABELS = ['All', 'Content', 'Setting', 'Format', 'Genre', 'System']
const activeTab = ref<'All' | 'Content' | 'Setting' | 'Format' | 'Genre' | 'System'>('All')
const filter = ref('')

const tagCounts = computed<Map<string, number>>(() => {
  const m = new Map<string, number>()
  if (!store.filters) return m
  for (const t of store.filters.tags) m.set(t.value, t.count)
  return m
})

const groups = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return TAG_GROUPS
    .filter(g => activeTab.value === 'All' || activeTab.value === g.label)
    .map(g => ({
      label: g.label,
      tags: g.tags
        .filter(t => tagCounts.value.has(t))
        .filter(t => !q || t.toLowerCase().includes(q))
        .map(t => ({ value: t, count: tagCounts.value.get(t) ?? 0 })),
    }))
    .filter(g => g.tags.length > 0)
})

const selectedTag = computed(() => store.activeFilters['tags'] ?? '')

function pick(tag: string) {
  store.setFilter('tags', selectedTag.value === tag ? '' : tag)
}

function clear() {
  store.setFilter('tags', '')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="open" class="overlay" @click.self="emit('close')">
    <div class="drawer" role="dialog" aria-modal="true" aria-label="Browse subjects">
      <div class="drawer-head">
        <span class="drawer-title">Subjects</span>
        <span class="drawer-status">
          <template v-if="selectedTag">{{ selectedTag }} selected · </template>esc to close
        </span>
      </div>

      <input
        v-model="filter"
        type="text"
        class="drawer-filter"
        placeholder="Filter subjects…"
        autofocus
      />

      <div class="drawer-tabs">
        <button
          v-for="tab in TAB_LABELS"
          :key="tab"
          :class="{ active: activeTab === tab }"
          @click="activeTab = tab as any"
        >{{ tab }}</button>
      </div>

      <div class="drawer-body">
        <div v-if="groups.length === 0" class="drawer-empty">No subjects match.</div>
        <div v-for="group in groups" :key="group.label" class="drawer-group">
          <div class="drawer-group-head">{{ group.label }}</div>
          <div class="drawer-tags">
            <button
              v-for="t in group.tags"
              :key="t.value"
              type="button"
              class="subj-chip"
              :class="{ 'is-selected': t.value === selectedTag }"
              @click="pick(t.value)"
            >
              <span class="subj-name">{{ t.value }}</span>
              <span class="subj-count">{{ t.count.toLocaleString() }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="drawer-foot">
        <span class="drawer-stat">
          <template v-if="selectedTag">1 subject filtering search</template>
          <template v-else>No subject selected</template>
        </span>
        <div class="drawer-actions">
          <button class="btn-secondary" @click="clear" :disabled="!selectedTag">Clear</button>
          <button class="btn-primary" @click="emit('close')">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(29, 29, 27, 0.35);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 80px;
  z-index: 100;
}

.drawer {
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 120px);
  background: var(--surface);
  border: 1px solid var(--line-hard);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 14px 18px 8px;
}
.drawer-title {
  font-family: var(--font-serif);
  font-size: var(--fs-lg);
  font-weight: 600;
  color: var(--text);
}
.drawer-status {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
}

.drawer-filter {
  margin: 0 18px 10px;
}

.drawer-tabs {
  display: flex;
  gap: 2px;
  padding: 0 18px;
  border-bottom: 1px solid var(--line);
}
.drawer-tabs button {
  background: transparent;
  border: none;
  padding: 8px 12px;
  font-size: var(--fs-sm);
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.drawer-tabs button:hover { color: var(--text); }
.drawer-tabs button.active {
  color: var(--text);
  border-bottom-color: var(--accent);
  font-weight: 500;
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 18px;
}

.drawer-empty {
  text-align: center;
  padding: 28px;
  color: var(--text-mute);
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
}

.drawer-group {
  margin-bottom: 18px;
}
.drawer-group-head {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-mute);
  margin-bottom: 8px;
}

.drawer-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.subj-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--chip-bg);
  color: var(--chip-text);
  font-family: var(--font-mono);
  font-size: var(--fs-xs);
  border: 1px solid transparent;
  cursor: pointer;
}
.subj-chip:hover { background: var(--line-hard); }
.subj-chip.is-selected {
  background: var(--text);
  color: var(--surface);
}
.subj-chip.is-selected .subj-count { color: rgba(255,255,255,0.65); }

.subj-name { font-weight: 500; }
.subj-count { color: var(--text-mute); font-size: 10px; }

.drawer-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 18px;
  border-top: 1px solid var(--line);
  background: var(--surface-alt);
}

.drawer-stat {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
}

.drawer-actions {
  display: flex;
  gap: 8px;
}
</style>
