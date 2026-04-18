<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useLibraryStore, type GraphResponse } from '../stores/library'

const router = useRouter()
const store = useLibraryStore()

const svgEl = ref<SVGSVGElement | null>(null)
const minScore = ref(0.25)
const limitNodes = ref(200)
const filterSystem = ref('')
const loading = ref(false)
const error = ref('')
const nodeCount = ref(0)
const edgeCount = ref(0)
const tooltip = ref<{ x: number; y: number; label: string; group: string | null } | null>(null)

// Color palette for game systems
const SYSTEM_COLORS: Record<string, string> = {
  'D&D 5e': '#4a90d9',
  'Pathfinder 1e': '#e67e22',
  'Pathfinder 2e': '#e74c3c',
  'OSR': '#27ae60',
  'Call of Cthulhu': '#8e44ad',
  'System Neutral': '#7f8c8d',
  'Universal': '#7f8c8d',
  'Dungeon Crawl Classics': '#d35400',
  'Year Zero Engine': '#16a085',
}
const DEFAULT_COLOR = '#666'

function systemColor(group: string | null): string {
  if (!group) return DEFAULT_COLOR
  return SYSTEM_COLORS[group] || DEFAULT_COLOR
}

let simulation: any = null
let d3: any = null

async function loadD3() {
  if (d3) return d3
  d3 = await import('d3')
  return d3
}

async function drawGraph(data: GraphResponse) {
  if (!svgEl.value) return
  const lib = await loadD3()

  const width = svgEl.value.clientWidth || 900
  const height = svgEl.value.clientHeight || 600

  // Clear previous
  lib.select(svgEl.value).selectAll('*').remove()

  if (data.nodes.length === 0) return

  const svg = lib.select(svgEl.value)
    .attr('width', width)
    .attr('height', height)

  // Zoom container
  const g = svg.append('g')
  svg.call(
    lib.zoom()
      .scaleExtent([0.1, 4])
      .on('zoom', (event: any) => g.attr('transform', event.transform))
  )

  // Build maps for D3 force (expects {id} objects)
  const nodeMap = new Map(data.nodes.map(n => [n.id, { ...n }]))
  const nodes: any[] = [...nodeMap.values()]
  const links: any[] = data.edges
    .filter(e => nodeMap.has(e.source) && nodeMap.has(e.target))
    .map(e => ({ source: e.source, target: e.target, score: e.score }))

  nodeCount.value = nodes.length
  edgeCount.value = links.length

  // Force simulation
  if (simulation) simulation.stop()
  simulation = lib.forceSimulation(nodes)
    .force('link', lib.forceLink(links).id((d: any) => d.id).distance(60))
    .force('charge', lib.forceManyBody().strength(-80))
    .force('center', lib.forceCenter(width / 2, height / 2))
    .force('collision', lib.forceCollide(8))

  // Draw edges
  const link = g.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', '#9b978c')
    .attr('stroke-width', (d: any) => Math.max(0.5, d.score * 3))
    .attr('stroke-opacity', 0.4)

  // Draw nodes
  const node = g.append('g')
    .selectAll('circle')
    .data(nodes)
    .join('circle')
    .attr('r', 5)
    .attr('fill', (d: any) => systemColor(d.group))
    .attr('stroke', '#ddd9d0')
    .attr('stroke-width', 0.7)
    .attr('cursor', 'pointer')
    .on('click', (_: any, d: any) => router.push({ name: 'book', params: { id: d.id } }))
    .on('mouseover', (event: MouseEvent, d: any) => {
      tooltip.value = {
        x: event.clientX + 10,
        y: event.clientY - 10,
        label: d.label,
        group: d.group,
      }
    })
    .on('mousemove', (event: MouseEvent) => {
      if (tooltip.value) {
        tooltip.value = { ...tooltip.value, x: event.clientX + 10, y: event.clientY - 10 }
      }
    })
    .on('mouseout', () => { tooltip.value = null })
    .call(
      lib.drag()
        .on('start', (event: any, d: any) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x; d.fy = d.y
        })
        .on('drag', (event: any, d: any) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event: any, d: any) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null; d.fy = null
        })
    )

  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)
    node
      .attr('cx', (d: any) => d.x)
      .attr('cy', (d: any) => d.y)
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await store.getGraph(
      minScore.value,
      limitNodes.value,
      filterSystem.value || undefined,
    )
    await drawGraph(data)
  } catch (e: any) {
    error.value = e.message || 'Failed to load graph. Run wiki_setup.py and relation_builder.py first.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
onUnmounted(() => { if (simulation) simulation.stop() })
</script>

<template>
  <div class="graph-page">
    <!-- Controls -->
    <div class="graph-controls">
      <div class="control-group">
        <label>Min similarity</label>
        <input type="range" v-model.number="minScore" min="0.1" max="0.9" step="0.05" @change="load" />
        <span class="control-value">{{ minScore.toFixed(2) }}</span>
      </div>
      <div class="control-group">
        <label>Max nodes</label>
        <input type="range" v-model.number="limitNodes" min="50" max="500" step="50" @change="load" />
        <span class="control-value">{{ limitNodes }}</span>
      </div>
      <div class="control-group">
        <label>System filter</label>
        <input
          v-model="filterSystem"
          type="text"
          placeholder="e.g. D&D 5e"
          class="system-filter"
          @keyup.enter="load"
        />
      </div>
      <button class="btn-primary" @click="load" :disabled="loading">
        {{ loading ? 'Loading...' : 'Reload' }}
      </button>
      <span class="graph-stats" v-if="nodeCount > 0">
        {{ nodeCount }} nodes · {{ edgeCount }} edges
      </span>
    </div>

    <!-- Legend -->
    <div class="legend">
      <span
        v-for="(color, sys) in { 'D&D 5e': '#4a90d9', 'Pathfinder 1e': '#e67e22', 'OSR': '#27ae60', 'Call of Cthulhu': '#8e44ad', 'System Neutral': '#7f8c8d', 'Other': '#666' }"
        :key="sys"
        class="legend-item"
      >
        <span class="legend-dot" :style="{ background: color }"></span>
        {{ sys }}
      </span>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- SVG Canvas -->
    <svg ref="svgEl" class="graph-canvas"></svg>

    <!-- Tooltip -->
    <div
      v-if="tooltip"
      class="tooltip"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      <div class="tooltip-title">{{ tooltip.label }}</div>
      <div class="tooltip-system" v-if="tooltip.group">{{ tooltip.group }}</div>
    </div>
  </div>
</template>

<style scoped>
.graph-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 52px);
  overflow: hidden;
}

.graph-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 10px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
  color: var(--text-dim);
}

.control-group label {
  white-space: nowrap;
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-mute);
}

.control-value {
  font-family: var(--font-mono);
  font-size: 11.5px;
  min-width: 2.5rem;
  text-align: right;
  color: var(--text);
}

.system-filter {
  width: 140px;
  font-size: var(--fs-sm);
  padding: 4px 8px;
}

.graph-stats {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-mute);
  margin-left: auto;
}

.legend {
  display: flex;
  gap: 14px;
  padding: 8px 16px;
  background: var(--surface-alt);
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-dim);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.error-msg {
  padding: 1rem;
  color: var(--danger);
  font-size: var(--fs-sm);
}

.graph-canvas {
  flex: 1;
  width: 100%;
  background: var(--bg);
}

.tooltip {
  position: fixed;
  background: var(--surface);
  border: 1px solid var(--line-hard);
  border-radius: var(--radius);
  padding: 6px 10px;
  pointer-events: none;
  z-index: 1000;
  max-width: 300px;
  box-shadow: var(--shadow-2);
}

.tooltip-title {
  font-size: var(--fs-sm);
  font-weight: 600;
  color: var(--text);
}

.tooltip-system {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-mute);
}
</style>
