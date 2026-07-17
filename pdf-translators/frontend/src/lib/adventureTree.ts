// Path-based block-tree logic for the Adventure Editor, ported from
// adventure_editor.py's vanilla JS. No Vue/DOM dependencies — kept pure so
// it stays trivially testable and the store can call it directly.
//
// Unlike the flat, leveled block array in lib/tree.ts (the Markdown Editor),
// the adventure block tree is a real nested tree: each block is either a
// plain string (a paragraph) or an object with a `type` and, for container
// types, an `entries` (or `items`, for lists) array of child blocks. A
// "path" identifies a block by the sequence of array indices / children-key
// strings you'd follow from the top-level `data` array to reach it, e.g.
// `[0, "entries", 2]` is the 3rd child of the top-level section at index 0.
// `pathKey`/`parsePath` serialize/deserialize a path to/from a JSON string
// so it can be used as a Map/Set key (path arrays aren't comparable by
// reference or `===`).
//
// Every mutation below clones the whole tree once (structuredClone) and
// edits the clone — this mirrors the original, which deep-cloned the tree
// on every `pushUndo()` anyway (to snapshot it for the undo log), just moved
// earlier. Precondition checks run against the *original* tree first, so a
// no-op (e.g. "can't move past the top") never pays for a clone.

export interface BlockNode {
  type: string
  name?: string
  entries?: TreeValue[]
  items?: unknown[]
  caption?: string
  colLabels?: string[]
  colStyles?: string[]
  rows?: string[][]
  href?: { type: string; path?: string }
  title?: string
  by?: string
  from?: string
  entry?: string
  id?: string
  _flags?: string[]
  [key: string]: unknown
}

export type TreeValue = string | BlockNode
export type PathSeg = number | string
export type NodePath = PathSeg[]

// ── Path serialization ──────────────────────────────────────────────────────

export function pathKey(path: NodePath): string {
  return JSON.stringify(path)
}

export function parsePath(key: string): NodePath {
  return JSON.parse(key)
}

// Ancestor *object* paths (not children-key paths) from root to (excluding)
// `path` itself — e.g. for [0,"entries",2,"entries",1] this is [[0],[0,"entries",2]].
// Used to expand every ancestor so a deeply nested node becomes visible.
export function ancestorPaths(path: NodePath): NodePath[] {
  const result: NodePath[] = []
  for (let i = 1; i < path.length; i += 2) result.push(path.slice(0, i))
  return result
}

// ── Raw path access ──────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function getByPath(data: TreeValue[], path: NodePath): any {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let obj: any = data
  for (const seg of path) {
    if (obj == null) return undefined
    obj = obj[seg as never]
  }
  return obj
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function setByPath(data: TreeValue[], path: NodePath, value: any): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let obj: any = data
  for (let i = 0; i < path.length - 1; i++) obj = obj[path[i] as never]
  obj[path[path.length - 1] as never] = value
}

export function deleteByPath(data: TreeValue[], path: NodePath): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let obj: any = data
  for (let i = 0; i < path.length - 1; i++) obj = obj[path[i] as never]
  const last = path[path.length - 1]
  if (Array.isArray(obj)) obj.splice(last as number, 1)
  else delete obj[last as never]
}

export function insertAfterPath(data: TreeValue[], path: NodePath, value: TreeValue): void {
  const parentPath = path.slice(0, -1)
  const idx = path[path.length - 1] as number
  const parent = parentPath.length === 0 ? data : getByPath(data, parentPath)
  if (Array.isArray(parent)) parent.splice(idx + 1, 0, value)
}

// The array containing the item *at* `path` (its siblings array).
export function getParentArray(data: TreeValue[], path: NodePath): TreeValue[] | undefined {
  if (path.length === 1) return data
  return getByPath(data, path.slice(0, -1))
}

// ── Node introspection ──────────────────────────────────────────────────────

export function getNodeType(node: TreeValue): string {
  if (typeof node === 'string') return 'string'
  if (node && node.type) return node.type
  return 'unknown'
}

export function getNodeName(node: TreeValue): string {
  if (typeof node === 'string') return node.length > 60 ? node.slice(0, 60) + '...' : node
  return node.name || ''
}

export function getChildrenKey(node: TreeValue): 'items' | 'entries' {
  return getNodeType(node) === 'list' ? 'items' : 'entries'
}

export function getChildren(node: TreeValue): TreeValue[] {
  if (typeof node === 'string') return []
  if (node.type === 'list') return (node.items as TreeValue[]) || []
  if (node.type === 'table' || node.type === 'hr' || node.type === 'image') return []
  return (node.entries as TreeValue[]) || []
}

export function hasChildren(node: TreeValue): boolean {
  return getChildren(node).length > 0
}

export function getNodeFlags(node: TreeValue): string[] {
  if (typeof node === 'string' || !node) return []
  return node._flags || []
}

// Total count of flagged nodes anywhere in the tree — backs the toolbar's
// "N flagged" indicator.
export function countFlagged(data: TreeValue[]): number {
  let count = 0
  function walk(nodes: TreeValue[]) {
    for (const n of nodes) {
      if (typeof n === 'string' || !n) continue
      if (n._flags && n._flags.length > 0) count++
      walk(getChildren(n))
    }
  }
  walk(data)
  return count
}

// ── Visible row flattening (drives the virtualized tree) ───────────────────

export interface VisibleRow {
  path: NodePath
  pk: string
  node: TreeValue
  depth: number
}

export function visibleRows(data: TreeValue[], collapsed: Set<string>): VisibleRow[] {
  const rows: VisibleRow[] = []
  function walk(node: TreeValue, path: NodePath, depth: number) {
    const pk = pathKey(path)
    rows.push({ path, pk, node, depth })
    const children = getChildren(node)
    if (children.length > 0 && !collapsed.has(pk)) {
      const childKey = getChildrenKey(node)
      children.forEach((child, i) => walk(child, [...path, childKey, i], depth + 1))
    }
  }
  data.forEach((node, i) => walk(node, [i], 0))
  return rows
}

// ── Single-node structural mutations ────────────────────────────────────────

export interface MoveResult {
  data: TreeValue[]
  newPath: NodePath | null
  uncollapsePath?: NodePath
}

// Lightweight precondition checks, split out so the tree panel can compute
// per-row button-disabled state without paying for a clone+mutate just to
// find out the operation would no-op.

export function canMove(data: TreeValue[], path: NodePath, direction: -1 | 1): boolean {
  const idx = path[path.length - 1] as number
  const parent = getParentArray(data, path)
  if (!Array.isArray(parent)) return false
  const newIdx = idx + direction
  return newIdx >= 0 && newIdx < parent.length
}

export function canPromote(data: TreeValue[], path: NodePath): boolean {
  if (path.length < 3) return false
  const parentArray = getParentArray(data, path)
  if (!Array.isArray(parentArray)) return false
  return Array.isArray(getParentArray(data, path.slice(0, -2)))
}

export function canDemote(data: TreeValue[], path: NodePath): boolean {
  const idx = path[path.length - 1] as number
  if (idx === 0) return false
  const parent = getParentArray(data, path)
  if (!Array.isArray(parent)) return false
  const prevSibling = parent[idx - 1]
  return !(typeof prevSibling === 'string' || !prevSibling)
}

export function moveNode(data: TreeValue[], path: NodePath, direction: -1 | 1): MoveResult {
  if (!canMove(data, path, direction)) return { data, newPath: null }
  const idx = path[path.length - 1] as number
  const newIdx = idx + direction

  const clone = structuredClone(data)
  const parent = getParentArray(clone, path) as TreeValue[]
  ;[parent[idx], parent[newIdx]] = [parent[newIdx], parent[idx]]
  return { data: clone, newPath: [...path.slice(0, -1), newIdx] }
}

// Move the node out of its parent, placing it after the parent in the
// grandparent array. No-op at top level (path.length < 3, i.e. no
// grandparent array exists to promote into).
export function promoteNode(data: TreeValue[], path: NodePath): MoveResult {
  if (!canPromote(data, path)) return { data, newPath: null }
  const idx = path[path.length - 1] as number
  const parentObjPath = path.slice(0, -2)

  const clone = structuredClone(data)
  const parentArray = getParentArray(clone, path) as TreeValue[]
  const node = parentArray.splice(idx, 1)[0]
  const grandparentArray = getParentArray(clone, parentObjPath) as TreeValue[]
  const parentIdx = parentObjPath[parentObjPath.length - 1] as number
  grandparentArray.splice(parentIdx + 1, 0, node)

  return { data: clone, newPath: [...parentObjPath.slice(0, -1), parentIdx + 1] }
}

// Nest the node into the preceding sibling's children. No-op if there's no
// preceding sibling, or the preceding sibling is a string (can't have children).
export function demoteNode(data: TreeValue[], path: NodePath): MoveResult {
  if (!canDemote(data, path)) return { data, newPath: null }
  const idx = path[path.length - 1] as number

  const clone = structuredClone(data)
  const parent = getParentArray(clone, path) as TreeValue[]
  const prevSibling = parent[idx - 1] as BlockNode
  const sibChildKey = getChildrenKey(prevSibling)
  if (!prevSibling[sibChildKey]) prevSibling[sibChildKey] = []
  const node = parent.splice(idx, 1)[0]
  ;(prevSibling[sibChildKey] as TreeValue[]).push(node)

  const sibPath = [...path.slice(0, -1), idx - 1]
  const newChildIdx = (prevSibling[sibChildKey] as TreeValue[]).length - 1
  return { data: clone, newPath: [...sibPath, sibChildKey, newChildIdx], uncollapsePath: sibPath }
}

export function deleteNode(data: TreeValue[], path: NodePath): TreeValue[] {
  const clone = structuredClone(data)
  deleteByPath(clone, path)
  return clone
}

// Remove the node, splicing its children into its place.
export function dissolveNode(data: TreeValue[], path: NodePath): TreeValue[] {
  const clone = structuredClone(data)
  const node = getByPath(clone, path)
  const childKey = getChildrenKey(node)
  const children = (node[childKey] as TreeValue[]) || []
  const idx = path[path.length - 1] as number
  const parent = getParentArray(clone, path) as TreeValue[]
  parent.splice(idx, 1, ...children)
  return clone
}

// ── Insertion ────────────────────────────────────────────────────────────────

export interface InsertResult {
  data: TreeValue[]
  newPath: NodePath
}

export function addTopLevelSection(data: TreeValue[], node: BlockNode): InsertResult {
  const clone = structuredClone(data)
  clone.push(node)
  return { data: clone, newPath: [clone.length - 1] }
}

export function addSiblingAfter(data: TreeValue[], path: NodePath, node: TreeValue): InsertResult {
  const clone = structuredClone(data)
  insertAfterPath(clone, path, node)
  return { data: clone, newPath: [...path.slice(0, -1), (path[path.length - 1] as number) + 1] }
}

export function addChildTo(data: TreeValue[], path: NodePath, node: TreeValue): InsertResult {
  const clone = structuredClone(data)
  const parentNode = getByPath(clone, path) as BlockNode
  const childKey = getChildrenKey(parentNode)
  if (!parentNode[childKey]) parentNode[childKey] = []
  ;(parentNode[childKey] as TreeValue[]).push(node)
  const newLen = (parentNode[childKey] as TreeValue[]).length
  return { data: clone, newPath: [...path, childKey, newLen - 1] }
}

// ── Generic buffered-edit commit ────────────────────────────────────────────

// Clone the tree, hand the node at `path` to `mutate` to edit in place, and
// return the clone. Backs every buffered "Done" commit (text/table/list/
// generic field edits) — the component holds local draft state and only
// calls this once, on commit, never per keystroke.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function replaceNode(data: TreeValue[], path: NodePath, mutate: (node: any) => void): TreeValue[] {
  const clone = structuredClone(data)
  mutate(getByPath(clone, path))
  return clone
}

export function setNode(data: TreeValue[], path: NodePath, value: TreeValue): TreeValue[] {
  const clone = structuredClone(data)
  setByPath(clone, path, value)
  return clone
}

// ── Flags ────────────────────────────────────────────────────────────────────

export function toggleFlag(data: TreeValue[], path: NodePath, flagId: string): TreeValue[] {
  return replaceNode(data, path, (node: BlockNode) => {
    if (!node || typeof node !== 'object') return
    if (!node._flags) node._flags = []
    const idx = node._flags.indexOf(flagId)
    if (idx >= 0) node._flags.splice(idx, 1)
    else node._flags.push(flagId)
    if (node._flags.length === 0) delete node._flags
  })
}

export function bulkFlag(data: TreeValue[], paths: NodePath[], flagId: string): TreeValue[] {
  const clone = structuredClone(data)
  for (const path of paths) {
    const node = getByPath(clone, path)
    if (!node || typeof node === 'string') continue
    if (!node._flags) node._flags = []
    if (!(node._flags as string[]).includes(flagId)) (node._flags as string[]).push(flagId)
  }
  return clone
}

export function bulkClearFlags(data: TreeValue[], paths: NodePath[]): TreeValue[] {
  const clone = structuredClone(data)
  for (const path of paths) {
    const node = getByPath(clone, path)
    if (!node || typeof node === 'string') continue
    delete node._flags
  }
  return clone
}

// ── Bulk (multi-select) operations ──────────────────────────────────────────
//
// `paths` must be sorted by *visible row order* ascending (i.e. the order
// blocks appear in the tree, top to bottom) — the store derives this from
// `visibleRows`. Delete/dissolve process in reverse so earlier splices don't
// invalidate later indices; move/promote/demote group by parent array first
// so a multi-parent selection moves each group independently.

export interface ParentGroup {
  parentPath: NodePath
  indices: number[]
  parent: TreeValue[]
}

export function groupByParent(data: TreeValue[], paths: NodePath[]): ParentGroup[] {
  const map = new Map<string, { parentPath: NodePath; indices: number[] }>()
  for (const path of paths) {
    const parentPath = path.slice(0, -1)
    const ppk = pathKey(parentPath)
    if (!map.has(ppk)) map.set(ppk, { parentPath, indices: [] })
    map.get(ppk)!.indices.push(path[path.length - 1] as number)
  }
  const groups: ParentGroup[] = []
  for (const g of map.values()) {
    g.indices.sort((a, b) => a - b)
    const parent = g.parentPath.length === 0 ? data : getByPath(data, g.parentPath)
    groups.push({ parentPath: g.parentPath, indices: g.indices, parent: parent as TreeValue[] })
  }
  return groups
}

export interface BulkMoveResult {
  data: TreeValue[]
  newSelection: string[]
}

export function bulkMove(data: TreeValue[], paths: NodePath[], direction: -1 | 1): BulkMoveResult {
  const clone = structuredClone(data)
  const groups = groupByParent(clone, paths)
  const newSelection: string[] = []
  for (const { parent, indices, parentPath } of groups) {
    let moved = true
    if (direction < 0) {
      if (indices[0] <= 0) moved = false
      else {
        const item = parent.splice(indices[0] - 1, 1)[0]
        parent.splice(indices[indices.length - 1], 0, item)
      }
    } else {
      if (indices[indices.length - 1] >= parent.length - 1) moved = false
      else {
        const item = parent.splice(indices[indices.length - 1] + 1, 1)[0]
        parent.splice(indices[0], 0, item)
      }
    }
    for (const oldIdx of indices) {
      newSelection.push(pathKey([...parentPath, moved ? oldIdx + direction : oldIdx]))
    }
  }
  return { data: clone, newSelection }
}

export function bulkDemote(data: TreeValue[], paths: NodePath[]): TreeValue[] {
  const clone = structuredClone(data)
  const groups = groupByParent(clone, paths)
  for (const { parent, indices } of groups) {
    const firstIdx = indices[0]
    if (firstIdx === 0) continue
    const target = parent[firstIdx - 1]
    if (typeof target === 'string' || !target) continue
    const targetKey = getChildrenKey(target)
    if (!target[targetKey]) target[targetKey] = []
    const nodes: TreeValue[] = []
    for (let i = indices.length - 1; i >= 0; i--) nodes.unshift(parent.splice(indices[i], 1)[0])
    ;(target[targetKey] as TreeValue[]).push(...nodes)
  }
  return clone
}

export function bulkPromote(data: TreeValue[], paths: NodePath[]): TreeValue[] {
  const clone = structuredClone(data)
  const groups = groupByParent(clone, paths)
  for (let g = groups.length - 1; g >= 0; g--) {
    const { parentPath, parent, indices } = groups[g]
    if (parentPath.length < 2) continue
    const parentObjPath = parentPath.slice(0, -1)
    const grandparentArray = getParentArray(clone, parentObjPath)
    if (!Array.isArray(grandparentArray)) continue
    const parentIdx = parentObjPath[parentObjPath.length - 1] as number
    const nodes: TreeValue[] = []
    for (let i = indices.length - 1; i >= 0; i--) nodes.unshift(parent.splice(indices[i], 1)[0])
    grandparentArray.splice(parentIdx + 1, 0, ...nodes)
  }
  return clone
}

export function bulkDelete(data: TreeValue[], sortedPaths: NodePath[]): TreeValue[] {
  const clone = structuredClone(data)
  for (let i = sortedPaths.length - 1; i >= 0; i--) deleteByPath(clone, sortedPaths[i])
  return clone
}

export function bulkDissolve(data: TreeValue[], sortedPaths: NodePath[]): TreeValue[] {
  const clone = structuredClone(data)
  for (let i = sortedPaths.length - 1; i >= 0; i--) {
    const path = sortedPaths[i]
    const node = getByPath(clone, path)
    if (typeof node === 'string') continue
    const childKey = getChildrenKey(node)
    const children = (node[childKey] as TreeValue[]) || []
    const idx = path[path.length - 1] as number
    const parent = getParentArray(clone, path) as TreeValue[]
    parent.splice(idx, 1, ...children)
  }
  return clone
}
