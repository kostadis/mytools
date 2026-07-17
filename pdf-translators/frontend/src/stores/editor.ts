import { defineStore } from 'pinia'
import {
  type Block,
  parseMarkdown,
  blocksToMarkdown,
  visibleIndices,
  sectionEnd,
  prevSibling,
  nextSibling,
  moveSectionUp,
  moveSectionDown,
  changeLevel,
  deleteSection,
} from '../lib/tree'

interface Snapshot {
  blocks: Block[]
  collapsed: number[]
  selected: number
  selection: number[]
}

interface State {
  blocks: Block[]
  collapsed: Set<number>
  selected: number // anchor / keyboard focus / preview-scroll target
  selection: Set<number> // all selected indices (multi-select)
  anchor: number // range anchor for shift-click (kept across shift-clicks)
  currentFile: string
  dirty: boolean
  statusMsg: string
  errorMsg: string
  undoStack: Snapshot[]
  redoStack: Snapshot[]
}

export const useEditor = defineStore('editor', {
  state: (): State => ({
    blocks: [],
    collapsed: new Set<number>(),
    selected: -1,
    selection: new Set<number>(),
    anchor: -1,
    currentFile: '',
    dirty: false,
    statusMsg: 'No file loaded.',
    errorMsg: '',
    undoStack: [],
    redoStack: [],
  }),

  getters: {
    // Flat list of visible row indices (respecting collapse) — the array the
    // virtualized tree renders. Recomputed only when blocks/collapsed change.
    visible(state): number[] {
      return visibleIndices(state.blocks, state.collapsed)
    },
    // Heading-only blocks for the preview pane, with their original index.
    headings(state): { idx: number; level: number; text: string }[] {
      const out: { idx: number; level: number; text: string }[] = []
      state.blocks.forEach((b, idx) => {
        if (b.level > 0) out.push({ idx, level: b.level, text: b.text })
      })
      return out
    },
    canUndo: (s) => s.undoStack.length > 0,
    canRedo: (s) => s.redoStack.length > 0,
    selectionCount: (s) => s.selection.size,
  },

  actions: {
    status(msg: string) {
      this.statusMsg = msg
    },

    dismissError() {
      this.errorMsg = ''
    },

    snapshot(): Snapshot {
      return {
        blocks: this.blocks.map((b) => ({ ...b })),
        collapsed: [...this.collapsed],
        selected: this.selected,
        selection: [...this.selection],
      }
    },

    pushHistory() {
      this.undoStack.push(this.snapshot())
      this.redoStack = []
      if (this.undoStack.length > 100) this.undoStack.shift()
    },

    applySnapshot(s: Snapshot) {
      this.blocks = s.blocks
      this.collapsed = new Set(s.collapsed)
      this.selected = s.selected
      this.selection = new Set(s.selection ?? (s.selected >= 0 ? [s.selected] : []))
      this.anchor = s.selected
    },

    undo() {
      if (!this.undoStack.length) return
      this.redoStack.push(this.snapshot())
      this.applySnapshot(this.undoStack.pop()!)
      this.dirty = true
    },

    redo() {
      if (!this.redoStack.length) return
      this.undoStack.push(this.snapshot())
      this.applySnapshot(this.redoStack.pop()!)
      this.dirty = true
    },

    // ── Selection / collapse (hot path; reactivity handles minimal repaint) ──

    // Plain single select (clears any multi-selection). Used by preview clicks.
    select(i: number) {
      this.selection = new Set([i])
      this.selected = i
      this.anchor = i
    },

    // Click with modifier keys: ctrl/cmd toggles one row; shift selects the
    // range (over *visible* rows) from the anchor; plain replaces with one.
    clickSelect(i: number, ctrl: boolean, shift: boolean) {
      if (shift && this.anchor >= 0) {
        const vis = this.visible
        const a = vis.indexOf(this.anchor)
        const b = vis.indexOf(i)
        if (a >= 0 && b >= 0) {
          const [lo, hi] = a < b ? [a, b] : [b, a]
          this.selection = new Set(vis.slice(lo, hi + 1))
          this.selected = i // anchor stays put so the range can be re-adjusted
          return
        }
      }
      if (ctrl) {
        const s = new Set(this.selection)
        if (s.has(i)) s.delete(i)
        else s.add(i)
        this.selection = s
        this.selected = i
        this.anchor = i
        return
      }
      this.select(i)
    },

    clearSelection() {
      this.selection = new Set()
    },

    selectAllVisible() {
      this.selection = new Set(this.visible)
    },

    toggleCollapse(i: number) {
      if (this.collapsed.has(i)) this.collapsed.delete(i)
      else this.collapsed.add(i)
      // reassign to trigger reactivity on the Set
      this.collapsed = new Set(this.collapsed)
    },

    // ── Structural mutations ─────────────────────────────────────────────────

    moveUp(i: number) {
      const ni = prevSibling(this.blocks, i)
      this.pushHistory()
      this.blocks = moveSectionUp(this.blocks, i)
      if (ni >= 0) this.selected = ni
      this.dirty = true
    },

    moveDown(i: number) {
      const ni = nextSibling(this.blocks, i)
      this.pushHistory()
      this.blocks = moveSectionDown(this.blocks, i)
      if (ni >= 0) this.selected = ni
      this.dirty = true
    },

    promote(i: number) {
      this.pushHistory()
      this.blocks = changeLevel(this.blocks, i, -1)
      this.dirty = true
    },

    demote(i: number) {
      this.pushHistory()
      this.blocks = changeLevel(this.blocks, i, 1)
      this.dirty = true
    },

    remove(i: number) {
      this.pushHistory()
      this.blocks = deleteSection(this.blocks, i)
      if (this.selected >= this.blocks.length) this.selected = this.blocks.length - 1
      this.dirty = true
    },

    renameHeading(i: number, text: string) {
      const t = text.trim()
      if (!t || t === this.blocks[i].text) return
      this.pushHistory()
      this.blocks = this.blocks.map((b, j) => (j === i ? { ...b, text: t } : b))
      this.dirty = true
    },

    // ── Bulk operations on the current multi-selection ───────────────────────

    // Promote/demote every selected heading by `delta`, clamped to 1..6.
    // Level changes don't shift indices, so a single map pass is safe.
    changeLevelSelected(delta: number) {
      if (!this.selection.size) return
      this.pushHistory()
      const sel = this.selection
      this.blocks = this.blocks.map((b, j) =>
        sel.has(j) && b.level > 0
          ? { ...b, level: Math.max(1, Math.min(6, b.level + delta)) }
          : b,
      )
      this.dirty = true
    },

    // Delete every selected section (heading + its subtree). Compute the union
    // of all [i, sectionEnd(i)) ranges first, then filter once — this is robust
    // to overlapping/nested selections (e.g. a parent and its child both held).
    deleteSelected() {
      if (!this.selection.size) return
      this.pushHistory()
      const remove = new Set<number>()
      for (const i of this.selection) {
        const end = sectionEnd(this.blocks, i)
        for (let j = i; j < end; j++) remove.add(j)
      }
      this.blocks = this.blocks.filter((_, j) => !remove.has(j))
      this.selection = new Set()
      this.selected = Math.min(this.selected, this.blocks.length - 1)
      this.anchor = this.selected
      this.dirty = true
    },

    // ── Load / save ──────────────────────────────────────────────────────────

    async load(path: string) {
      const r = await fetch('/api/md/load?file=' + encodeURIComponent(path))
      if (!r.ok) {
        const body = await r.json().catch(() => null)
        const msg = body?.error || `Load failed: ${path}`
        this.status(msg)
        this.errorMsg = msg
        return
      }
      const data = await r.json()
      this.currentFile = data.path
      this.blocks = parseMarkdown(data.content)
      this.collapsed = new Set()
      this.selected = -1
      this.selection = new Set()
      this.anchor = -1
      this.undoStack = []
      this.redoStack = []
      this.dirty = false
      this.errorMsg = ''
      this.status(`Loaded: ${data.path.split('/').pop()}  (${this.blocks.length} blocks)`)
    },

    async save() {
      if (!this.currentFile) {
        this.status('No file loaded.')
        return
      }
      const md = blocksToMarkdown(this.blocks)
      const r = await fetch('/api/md/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile, content: md }),
      })
      if (r.ok) {
        this.dirty = false
        this.errorMsg = ''
        this.status('Saved ✓')
      } else {
        const body = await r.json().catch(() => null)
        const msg = body?.error || 'Save failed!'
        this.status(msg)
        this.errorMsg = msg
      }
    },
  },
})
