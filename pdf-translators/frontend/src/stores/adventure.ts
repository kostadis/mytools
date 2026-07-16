import { defineStore } from 'pinia'
import * as Tree from '../lib/adventureTree'
import type { NodePath, TreeValue } from '../lib/adventureTree'

interface HistoryEntry {
  idx: number
  ts: number
  action: string
}

interface Meta {
  name: string
  source: string
}

interface State {
  data: TreeValue[]
  collapsed: Set<string>
  selectedPath: string | null // row with an open edit form
  selection: Set<string> // multi-select
  anchor: string | null // shift-click range anchor
  currentFile: string
  meta: Meta
  dirty: boolean
  statusMsg: string
  errorMsg: string
  undoPosition: number
  undoTotal: number
  historyEntries: HistoryEntry[]
  lastActiveTextarea: HTMLTextAreaElement | HTMLInputElement | null
}

export const useAdventure = defineStore('adventure', {
  state: (): State => ({
    data: [],
    collapsed: new Set<string>(),
    selectedPath: null,
    selection: new Set<string>(),
    anchor: null,
    currentFile: '',
    meta: { name: '', source: '' },
    dirty: false,
    statusMsg: 'No file loaded.',
    errorMsg: '',
    undoPosition: -1,
    undoTotal: 0,
    historyEntries: [],
    lastActiveTextarea: null,
  }),

  getters: {
    visible(state): Tree.VisibleRow[] {
      return Tree.visibleRows(state.data, state.collapsed)
    },
    flagCount(state): number {
      return Tree.countFlagged(state.data)
    },
    canUndo: (s) => s.undoPosition >= 0,
    canRedo: (s) => s.undoPosition + 1 < s.undoTotal,
    selectionCount: (s) => s.selection.size,
  },

  actions: {
    status(msg: string) {
      this.statusMsg = msg
    },

    dismissError() {
      this.errorMsg = ''
    },

    setLastActiveTextarea(el: HTMLTextAreaElement | HTMLInputElement | null) {
      this.lastActiveTextarea = el
    },

    // ── Undo log (server-persisted) ─────────────────────────────────────────
    // Snapshots the CURRENT (pre-mutation) `data` — call before applying a
    // mutation, matching the disk-backed log's push-then-apply contract.
    _pushUndo(action: string) {
      fetch('/api/adv/undolog/push', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile, action, data: this.data }),
      })
        .then((r) => r.json())
        .then((res) => {
          if (res.ok) {
            this.undoPosition = res.position
            this.undoTotal = res.total
            this.refreshHistory()
          }
        })
        .catch(() => {})
    },

    async refreshHistory() {
      if (!this.currentFile) return
      const r = await fetch(`/api/adv/undolog?path=${encodeURIComponent(this.currentFile)}`)
      if (!r.ok) return
      const result = await r.json()
      this.historyEntries = result.entries || []
      this.undoPosition = result.position ?? -1
      this.undoTotal = this.historyEntries.length
    },

    async undo() {
      if (!this.currentFile) return
      const r = await fetch('/api/adv/undolog/undo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile }),
      })
      const result = await r.json()
      if (!r.ok || result.error) {
        this.status('Undo: ' + (result.error || 'failed'))
        return
      }
      this.data = result.data
      this.undoPosition = result.position
      this.undoTotal = result.total
      this.selectedPath = null
      this.selection = new Set()
      this.dirty = true
      await this.refreshHistory()
      this.status(`Undid: ${result.action}`)
    },

    async redo() {
      if (!this.currentFile) return
      const r = await fetch('/api/adv/undolog/redo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile }),
      })
      const result = await r.json()
      if (!r.ok || result.error) {
        this.status('Redo: ' + (result.error || 'failed'))
        return
      }
      this.data = result.data
      this.undoPosition = result.position
      this.undoTotal = result.total
      this.selectedPath = null
      this.selection = new Set()
      this.dirty = true
      await this.refreshHistory()
      this.status(`Redid: ${result.action}`)
    },

    async jumpToUndo(idx: number) {
      if (!this.currentFile) return
      const r = await fetch('/api/adv/undolog/jump', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile, idx }),
      })
      const result = await r.json()
      if (!r.ok || result.error) {
        this.status(result.error || 'Jump failed')
        return
      }
      this.data = result.data
      this.undoPosition = result.position
      this.undoTotal = result.total
      this.selectedPath = null
      this.selection = new Set()
      this.dirty = true
      await this.refreshHistory()
      this.status(`Jumped to: ${result.action}`)
    },

    // ── Load / save ──────────────────────────────────────────────────────────

    async load(path: string) {
      const r = await fetch('/api/adv/load', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      const result = await r.json()
      if (!r.ok || result.error) {
        const msg = result.error || `Load failed: ${path}`
        this.status(msg)
        this.errorMsg = msg
        return
      }
      this.currentFile = path
      this.data = result.data
      this.meta = result.meta
      this.selectedPath = null
      this.selection = new Set()
      this.anchor = null
      this.collapsed = new Set()
      this.dirty = false
      this.errorMsg = ''
      this.historyEntries = result.undolog?.entries ?? []
      this.undoPosition = result.undolog?.position ?? -1
      this.undoTotal = this.historyEntries.length
      const logMsg = this.undoTotal > 0 ? ` (${this.undoTotal} undo entries loaded)` : ''
      this.status(`Loaded: ${result.meta.name || path} (${this.data.length} sections)${logMsg}`)
    },

    async save() {
      if (!this.currentFile) {
        this.status('No file loaded.')
        return
      }
      const r = await fetch('/api/adv/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile, data: this.data }),
      })
      const result = await r.json()
      if (r.ok && result.ok) {
        this.dirty = false
        this.errorMsg = ''
        const warnCount = (result.warnings || []).length
        if (warnCount > 0) this.status(`Saved with ${warnCount} fix(es): ${result.warnings[0]}`)
        else this.status(`Saved: ${result.sections} sections, ${result.toc_entries} TOC entries`)
      } else {
        const msg = result.error || 'Save failed!'
        this.status(msg)
        this.errorMsg = msg
      }
    },

    // ── Selection / collapse ────────────────────────────────────────────────

    select(pk: string) {
      this.selection = new Set()
      this.selectedPath = this.selectedPath === pk ? null : pk
      this.anchor = pk
    },

    clickSelect(pk: string, ctrl: boolean, shift: boolean) {
      if (shift && this.anchor) {
        const vis = this.visible.map((r) => r.pk)
        const a = vis.indexOf(this.anchor)
        const b = vis.indexOf(pk)
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a]
          this.selection = new Set(vis.slice(lo, hi + 1))
          this.selectedPath = pk
          return
        }
      }
      if (ctrl) {
        const s = new Set(this.selection)
        if (s.has(pk)) s.delete(pk)
        else s.add(pk)
        this.selection = s
        this.selectedPath = pk
        this.anchor = pk
        return
      }
      this.select(pk)
    },

    clearSelection() {
      this.selection = new Set()
    },

    cancelEdit() {
      this.selectedPath = null
    },

    toggleCollapse(pk: string) {
      const c = new Set(this.collapsed)
      if (c.has(pk)) c.delete(pk)
      else c.add(pk)
      this.collapsed = c
    },

    collapseAll() {
      const all = Tree.visibleRows(this.data, new Set())
      this.collapsed = new Set(all.filter((r) => Tree.hasChildren(r.node)).map((r) => r.pk))
    },

    expandAll() {
      this.collapsed = new Set()
    },

    expandToLevel(maxDepth: number) {
      const all = Tree.visibleRows(this.data, new Set())
      this.collapsed = new Set(
        all.filter((r) => Tree.hasChildren(r.node) && r.depth >= maxDepth).map((r) => r.pk),
      )
    },

    jumpToFlag(direction: 1 | -1) {
      const vis = this.visible
      const flaggedRows = vis
        .map((r, i) => (Tree.getNodeFlags(r.node).length > 0 ? i : -1))
        .filter((i) => i >= 0)
      if (flaggedRows.length === 0) {
        this.status('No flagged entries')
        return
      }
      const currentRow = this.selectedPath ? vis.findIndex((r) => r.pk === this.selectedPath) : -1
      let targetRow: number | undefined
      if (direction > 0) {
        targetRow = flaggedRows.find((r) => r > currentRow)
        if (targetRow === undefined) targetRow = flaggedRows[0]
      } else {
        for (let i = flaggedRows.length - 1; i >= 0; i--) {
          if (flaggedRows[i] < currentRow) {
            targetRow = flaggedRows[i]
            break
          }
        }
        if (targetRow === undefined) targetRow = flaggedRows[flaggedRows.length - 1]
      }
      const pk = vis[targetRow].pk
      this.selection = new Set()
      this.selectedPath = pk
      this.anchor = pk
      const c = new Set(this.collapsed)
      for (const ap of Tree.ancestorPaths(Tree.parsePath(pk))) c.delete(Tree.pathKey(ap))
      this.collapsed = c
    },

    // ── Single-node structural mutations ────────────────────────────────────

    moveUp(pk: string) {
      const r = Tree.moveNode(this.data, Tree.parsePath(pk), -1)
      if (!r.newPath) return
      this._pushUndo('Move up')
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    moveDown(pk: string) {
      const r = Tree.moveNode(this.data, Tree.parsePath(pk), 1)
      if (!r.newPath) return
      this._pushUndo('Move down')
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    promote(pk: string) {
      const r = Tree.promoteNode(this.data, Tree.parsePath(pk))
      if (!r.newPath) return
      this._pushUndo('Promote (outdent)')
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    demote(pk: string) {
      const r = Tree.demoteNode(this.data, Tree.parsePath(pk))
      if (!r.newPath) return
      this._pushUndo('Demote (indent)')
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      if (r.uncollapsePath) {
        const c = new Set(this.collapsed)
        c.delete(Tree.pathKey(r.uncollapsePath))
        this.collapsed = c
      }
      this.dirty = true
    },

    remove(pk: string) {
      this._pushUndo('Delete block')
      this.data = Tree.deleteNode(this.data, Tree.parsePath(pk))
      this.selectedPath = null
      this.dirty = true
    },

    dissolve(pk: string) {
      this._pushUndo('Dissolve block')
      this.data = Tree.dissolveNode(this.data, Tree.parsePath(pk))
      this.selectedPath = null
      this.dirty = true
    },

    toggleFlag(pk: string, flagId: string) {
      this._pushUndo(`Toggle flag: ${flagId}`)
      this.data = Tree.toggleFlag(this.data, Tree.parsePath(pk), flagId)
    },

    // ── Insertion ────────────────────────────────────────────────────────────

    addTopLevelSection() {
      this._pushUndo('Add section')
      const r = Tree.addTopLevelSection(this.data, { type: 'section', name: 'New Section', entries: [] })
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    addSibling(pk: string, newNode: TreeValue) {
      this._pushUndo(`Add ${Tree.getNodeType(newNode)}`)
      const r = Tree.addSiblingAfter(this.data, Tree.parsePath(pk), newNode)
      this.data = r.data
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    addChild(pk: string, newNode: TreeValue) {
      this._pushUndo(`Add child ${Tree.getNodeType(newNode)}`)
      const r = Tree.addChildTo(this.data, Tree.parsePath(pk), newNode)
      this.data = r.data
      const c = new Set(this.collapsed)
      c.delete(pk)
      this.collapsed = c
      this.selectedPath = Tree.pathKey(r.newPath)
      this.dirty = true
    },

    // ── Buffered edit commits ────────────────────────────────────────────────
    // `keepOpen` covers table/list structural ops (add/remove row, col, item),
    // which commit immediately and leave the form open — everything else
    // (the "Done" button) commits once and closes the form.

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    commitNode(pk: string, label: string, mutate: (node: any) => void, keepOpen = false) {
      this._pushUndo(label)
      this.data = Tree.replaceNode(this.data, Tree.parsePath(pk), mutate)
      if (!keepOpen) this.selectedPath = null
      this.dirty = true
    },

    setNodeValue(pk: string, value: TreeValue, label = 'Edit text') {
      this._pushUndo(label)
      this.data = Tree.setNode(this.data, Tree.parsePath(pk), value)
      this.selectedPath = null
      this.dirty = true
    },

    // ── Bulk (multi-select) operations ──────────────────────────────────────

    _sortedSelectionPaths(): NodePath[] {
      const order = this.visible.map((r) => r.pk)
      return [...this.selection]
        .sort((a, b) => order.indexOf(a) - order.indexOf(b))
        .map((pk) => Tree.parsePath(pk))
    },

    bulkMove(direction: 1 | -1) {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Move ${paths.length} blocks ${direction < 0 ? 'up' : 'down'}`)
      const r = Tree.bulkMove(this.data, paths, direction)
      this.data = r.data
      this.selection = new Set(r.newSelection)
      this.selectedPath = null
      this.dirty = true
    },

    bulkDemote() {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Demote ${paths.length} blocks`)
      this.data = Tree.bulkDemote(this.data, paths)
      this.selection = new Set()
      this.selectedPath = null
      this.dirty = true
    },

    bulkPromote() {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Promote ${paths.length} blocks`)
      this.data = Tree.bulkPromote(this.data, paths)
      this.selection = new Set()
      this.selectedPath = null
      this.dirty = true
    },

    bulkDelete() {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Delete ${paths.length} blocks`)
      this.data = Tree.bulkDelete(this.data, paths)
      this.selection = new Set()
      this.selectedPath = null
      this.dirty = true
    },

    bulkDissolve() {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Dissolve ${paths.length} blocks`)
      this.data = Tree.bulkDissolve(this.data, paths)
      this.selection = new Set()
      this.selectedPath = null
      this.dirty = true
    },

    bulkFlag(flagId: string) {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Flag ${paths.length} blocks: ${flagId}`)
      this.data = Tree.bulkFlag(this.data, paths, flagId)
      this.selection = new Set()
      this.dirty = true
    },

    bulkClearFlags() {
      const paths = this._sortedSelectionPaths()
      if (!paths.length) return
      this._pushUndo(`Clear flags from ${paths.length} blocks`)
      this.data = Tree.bulkClearFlags(this.data, paths)
      this.selection = new Set()
      this.dirty = true
    },
  },
})
