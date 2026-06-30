import { defineStore } from 'pinia'
import {
  type Block,
  parseMarkdown,
  blocksToMarkdown,
  visibleIndices,
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
}

interface State {
  blocks: Block[]
  collapsed: Set<number>
  selected: number
  currentFile: string
  dirty: boolean
  statusMsg: string
  undoStack: Snapshot[]
  redoStack: Snapshot[]
}

export const useEditor = defineStore('editor', {
  state: (): State => ({
    blocks: [],
    collapsed: new Set<number>(),
    selected: -1,
    currentFile: '',
    dirty: false,
    statusMsg: 'No file loaded.',
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
  },

  actions: {
    status(msg: string) {
      this.statusMsg = msg
    },

    snapshot(): Snapshot {
      return {
        blocks: this.blocks.map((b) => ({ ...b })),
        collapsed: [...this.collapsed],
        selected: this.selected,
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

    select(i: number) {
      this.selected = i
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

    // ── Load / save ──────────────────────────────────────────────────────────

    async load(path: string) {
      const r = await fetch('/api/load?file=' + encodeURIComponent(path))
      if (!r.ok) {
        this.status('Load failed: ' + path)
        return
      }
      const data = await r.json()
      this.currentFile = data.path
      this.blocks = parseMarkdown(data.content)
      this.collapsed = new Set()
      this.selected = -1
      this.undoStack = []
      this.redoStack = []
      this.dirty = false
      this.status(`Loaded: ${data.path.split('/').pop()}  (${this.blocks.length} blocks)`)
    },

    async save() {
      if (!this.currentFile) {
        this.status('No file loaded.')
        return
      }
      const md = blocksToMarkdown(this.blocks)
      const r = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: this.currentFile, content: md }),
      })
      if (r.ok) {
        this.dirty = false
        this.status('Saved ✓')
      } else {
        this.status('Save failed!')
      }
    },
  },
})
