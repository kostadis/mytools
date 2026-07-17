<script setup lang="ts">
import { computed } from 'vue'
import { useAdventure } from '../../stores/adventure'
import * as Tree from '../../lib/adventureTree'
import { escapeHtml } from '../../lib/textUtils'
import { renderTags } from '../../lib/tagRender'

const props = defineProps<{
  node: Tree.TreeValue
  path: Tree.NodePath
  depth: number
}>()

const store = useAdventure()

const pk = computed(() => Tree.pathKey(props.path))
const type = computed(() => Tree.getNodeType(props.node))
const n = computed(() => props.node as Tree.BlockNode)
const highlighted = computed(() => store.selectionCount === 0 && store.selectedPath === pk.value)

function rt(s: string | undefined): string {
  return renderTags(escapeHtml(s || ''))
}

interface ChildRow {
  node: Tree.TreeValue
  path: Tree.NodePath
}

function childRows(childKey: 'entries' | 'items'): ChildRow[] {
  const children = (n.value[childKey] as Tree.TreeValue[]) || []
  return children.map((child, i) => ({ node: child, path: [...props.path, childKey, i] }))
}

const entriesHeadingLevel = computed(() => Math.min(props.depth + 3, 5))
</script>

<template>
  <p v-if="type === 'string'" class="apv-para" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk" v-html="rt(node as string)" />

  <hr v-else-if="type === 'hr'" class="apv-hr" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk" />

  <div v-else-if="type === 'section'" class="apv-section" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <h2 v-html="rt(n.name)" />
    <PreviewNode v-for="c in childRows('entries')" :key="Tree.pathKey(c.path)" :node="c.node" :path="c.path" :depth="depth" />
  </div>

  <div v-else-if="type === 'entries'" class="apv-entries" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <component :is="'h' + entriesHeadingLevel" v-if="n.name" v-html="rt(n.name)" />
    <PreviewNode v-for="c in childRows('entries')" :key="Tree.pathKey(c.path)" :node="c.node" :path="c.path" :depth="depth + 1" />
  </div>

  <div v-else-if="type === 'inset'" class="apv-inset" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <div v-if="n.name" class="apv-inset-title" v-html="rt(n.name)" />
    <PreviewNode v-for="c in childRows('entries')" :key="Tree.pathKey(c.path)" :node="c.node" :path="c.path" :depth="depth" />
  </div>

  <div v-else-if="type === 'insetReadaloud'" class="apv-readaloud" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <PreviewNode v-for="c in childRows('entries')" :key="Tree.pathKey(c.path)" :node="c.node" :path="c.path" :depth="depth" />
  </div>

  <ul v-else-if="type === 'list'" class="apv-list" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <li v-for="(item, i) in (n.items || [])" :key="i">
      <template v-if="typeof item === 'string'">
        <span v-html="rt(item)" />
      </template>
      <template v-else-if="item && (item as Tree.BlockNode).type === 'item'">
        <b v-if="(item as Tree.BlockNode).name" v-html="rt((item as Tree.BlockNode).name)" />{{ ' ' }}<span v-html="rt((item as Tree.BlockNode).entry)" />
      </template>
      <template v-else>
        <span v-html="rt(JSON.stringify(item))" />
      </template>
    </li>
  </ul>

  <table v-else-if="type === 'table'" class="apv-table" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <caption v-if="n.caption" v-html="rt(n.caption)" />
    <thead v-if="n.colLabels && n.colLabels.length">
      <tr>
        <th v-for="(col, i) in n.colLabels" :key="i" v-html="rt(col)" />
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, r) in n.rows || []" :key="r">
        <td v-for="(cell, c) in row" :key="c" v-html="rt(String(cell))" />
      </tr>
    </tbody>
  </table>

  <div v-else-if="type === 'image'" class="apv-image" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    [Image: {{ n.title || n.href?.path || 'Image' }}]
  </div>

  <div v-else-if="type === 'quote'" class="apv-quote" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <p v-for="(e, i) in (n.entries || []).filter((e) => typeof e === 'string')" :key="i" v-html="rt(e as string)" />
    <div v-if="n.by || n.from" class="apv-quote-by">
      — <template v-if="n.by">{{ n.by }}</template><template v-if="n.from">, <i>{{ n.from }}</i></template>
    </div>
  </div>

  <div v-else-if="n.entries" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">
    <b v-if="n.name" v-html="rt(n.name)" />
    <PreviewNode v-for="c in childRows('entries')" :key="Tree.pathKey(c.path)" :node="c.node" :path="c.path" :depth="depth" />
  </div>

  <p v-else class="apv-para apv-unknown" :class="{ 'apv-highlight': highlighted }" :data-pv-path="pk">[{{ type }}]</p>
</template>
