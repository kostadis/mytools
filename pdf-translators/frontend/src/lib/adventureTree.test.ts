import { describe, expect, it } from 'vitest'
import {
  type BlockNode,
  type TreeValue,
  bulkDelete,
  bulkDemote,
  bulkDissolve,
  bulkFlag,
  bulkMove,
  bulkPromote,
  bulkClearFlags,
  countFlagged,
  demoteNode,
  dissolveNode,
  getNodeFlags,
  moveNode,
  promoteNode,
  toggleFlag,
} from './adventureTree'

function makeTestData(): TreeValue[] {
  return [
    {
      type: 'section',
      name: 'Chapter 1',
      entries: [
        'Para 1',
        { type: 'entries', name: 'Room A', entries: ['Room A text.'] },
        { type: 'entries', name: 'Room B', entries: ['Room B text.'] },
      ],
    },
    {
      type: 'section',
      name: 'Chapter 2',
      entries: [{ type: 'entries', name: 'Room C', entries: ['Room C text.'] }],
    },
  ]
}

function node(v: TreeValue): BlockNode {
  return v as BlockNode
}

describe('moveNode', () => {
  it('moves a top-level section down', () => {
    const data = makeTestData()
    const r = moveNode(data, [0], 1)
    expect(node(r.data[0]).name).toBe('Chapter 2')
    expect(node(r.data[1]).name).toBe('Chapter 1')
  })

  it('moves a top-level section back up', () => {
    const data = makeTestData()
    const down = moveNode(data, [0], 1)
    const up = moveNode(down.data, [1], -1)
    expect(node(up.data[0]).name).toBe('Chapter 1')
  })

  it('moves a nested entry down', () => {
    const data = makeTestData()
    const r = moveNode(data, [0, 'entries', 1], 1)
    const entries = node(r.data[0]).entries!
    expect(node(entries[1]).name).toBe('Room B')
    expect(node(entries[2]).name).toBe('Room A')
  })

  it('does nothing at the boundary', () => {
    const data = makeTestData()
    const r = moveNode(data, [1], 1)
    expect(r.newPath).toBeNull()
  })
})

describe('promoteNode', () => {
  it('promotes a nested entry to section level', () => {
    const data = makeTestData()
    const r = promoteNode(data, [0, 'entries', 2])
    expect(r.newPath).not.toBeNull()
    expect(node(r.data[1]).name).toBe('Room B')
    expect(node(r.data[2]).name).toBe('Chapter 2')
    expect(node(r.data[0]).entries).toHaveLength(2)
  })

  it('is a no-op at the top level', () => {
    const data = makeTestData()
    const r = promoteNode(data, [0])
    expect(r.newPath).toBeNull()
  })

  it('promotes a deeply nested entry', () => {
    const data = makeTestData()
    const roomA = node(node(data[0]).entries![1])
    roomA.entries!.push({ type: 'entries', name: 'SubRoom', entries: [] })
    const r = promoteNode(data, [0, 'entries', 1, 'entries', 1])
    const entries = node(r.data[0]).entries!
    expect(node(entries[2]).name).toBe('SubRoom')
    expect(node(entries[3]).name).toBe('Room B')
  })
})

describe('demoteNode', () => {
  it('nests an entry into its preceding sibling', () => {
    const data = makeTestData()
    const r = demoteNode(data, [0, 'entries', 2])
    expect(r.newPath).not.toBeNull()
    const roomA = node(node(r.data[0]).entries![1])
    expect(roomA.name).toBe('Room A')
    const roomAEntries = roomA.entries!
    expect(node(roomAEntries[roomAEntries.length - 1]).name).toBe('Room B')
    expect(node(r.data[0]).entries).toHaveLength(2)
  })

  it('is a no-op for the first entry (no preceding sibling)', () => {
    const data = makeTestData()
    const r = demoteNode(data, [0, 'entries', 0])
    expect(r.newPath).toBeNull()
  })

  it('is a no-op when the preceding sibling is a string', () => {
    const data = makeTestData()
    const r = demoteNode(data, [0, 'entries', 1])
    expect(r.newPath).toBeNull()
  })

  it('demotes a top-level section into its preceding sibling', () => {
    const data = makeTestData()
    const r = demoteNode(data, [1])
    expect(r.data).toHaveLength(1)
    const entries = node(r.data[0]).entries!
    expect(node(entries[entries.length - 1]).name).toBe('Chapter 2')
  })

  it('promote then demote round-trips to an equivalent structure', () => {
    const original = makeTestData()
    const promoted = promoteNode(original, [0, 'entries', 2])
    const demoted = demoteNode(promoted.data, promoted.newPath!)
    expect(demoted.data).toHaveLength(original.length)
    expect(node(demoted.data[0]).entries).toHaveLength(node(original[0]).entries!.length)
  })
})

describe('dissolveNode', () => {
  it('promotes a section subtree children to its own position', () => {
    const data = makeTestData()
    const result = dissolveNode(data, [0])
    expect(result).toHaveLength(4)
    expect(result[0]).toBe('Para 1')
    expect(node(result[1]).name).toBe('Room A')
    expect(node(result[2]).name).toBe('Room B')
    expect(node(result[3]).name).toBe('Chapter 2')
  })

  it('dissolves a nested entry into its parent', () => {
    const data = makeTestData()
    const result = dissolveNode(data, [0, 'entries', 1])
    const entries = node(result[0]).entries!
    expect(entries).toHaveLength(3)
    expect(entries[0]).toBe('Para 1')
    expect(entries[1]).toBe('Room A text.')
    expect(node(entries[2]).name).toBe('Room B')
  })

  it('just removes the node when it has no children', () => {
    const data = makeTestData()
    node(node(data[0]).entries![2]).entries = []
    const result = dissolveNode(data, [0, 'entries', 2])
    expect(node(result[0]).entries).toHaveLength(2)
  })

  it('preserves sibling order after the dissolved node', () => {
    const data = makeTestData()
    const chapter2 = node(data[1])
    const roomCCount = node(chapter2.entries![0]).entries!.length
    chapter2.entries!.push({ type: 'entries', name: 'Room D', entries: ['Room D text.'] })
    const result = dissolveNode(data, [1, 'entries', 0])
    const entries = node(result[1]).entries!
    expect(node(entries[entries.length - 1]).name).toBe('Room D')
    expect(entries).toHaveLength(roomCCount + 1)
  })
})

describe('bulkDemote', () => {
  it('skips a group whose target is a string', () => {
    const data = makeTestData()
    const result = bulkDemote(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    expect(node(result[0]).entries).toHaveLength(3)
  })

  it('demotes a consecutive range into a single target, flat (no cascading)', () => {
    const data: TreeValue[] = [
      {
        type: 'section',
        name: 'S',
        entries: ['A', 'B', 'C', 'D', 'E'].map((name) => ({ type: 'entries', name, entries: [] })),
      },
    ]
    const result = bulkDemote(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
      [0, 'entries', 3],
    ])
    const entries = node(result[0]).entries!
    expect(entries).toHaveLength(2)
    expect(node(entries[0]).name).toBe('A')
    expect(node(entries[1]).name).toBe('E')
    const aChildren = node(entries[0]).entries!
    expect(aChildren.map((c) => node(c).name)).toEqual(['B', 'C', 'D'])
  })

  it('demotes top-level sections', () => {
    const data = makeTestData()
    const result = bulkDemote(data, [[1]])
    expect(result).toHaveLength(1)
    const entries = node(result[0]).entries!
    expect(node(entries[entries.length - 1]).name).toBe('Chapter 2')
  })

  it('preserves original order in the target', () => {
    const data: TreeValue[] = [
      {
        type: 'section',
        name: 'S',
        entries: ['X', 'A', 'B', 'C'].map((name) => ({ type: 'entries', name, entries: [] })),
      },
    ]
    const result = bulkDemote(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
      [0, 'entries', 3],
    ])
    const xChildren = node(node(result[0]).entries![0]).entries!
    expect(xChildren.map((c) => node(c).name)).toEqual(['A', 'B', 'C'])
  })
})

describe('bulkPromote', () => {
  it('promotes multiple siblings out of the same parent', () => {
    const data = makeTestData()
    const result = bulkPromote(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    expect(result).toHaveLength(4)
    expect(node(result[0]).name).toBe('Chapter 1')
    expect(node(result[1]).name).toBe('Room A')
    expect(node(result[2]).name).toBe('Room B')
    expect(node(result[3]).name).toBe('Chapter 2')
    expect(node(result[0]).entries).toEqual(['Para 1'])
  })

  it('is a no-op for top-level selections', () => {
    const data = makeTestData()
    const result = bulkPromote(data, [[0], [1]])
    expect(result).toHaveLength(data.length)
  })

  it('preserves original order in the grandparent', () => {
    const data: TreeValue[] = [
      {
        type: 'section',
        name: 'S',
        entries: ['A', 'B', 'C'].map((name) => ({ type: 'entries', name, entries: [] })),
      },
    ]
    const result = bulkPromote(data, [
      [0, 'entries', 0],
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    expect(result.map((n) => node(n).name)).toEqual(['S', 'A', 'B', 'C'])
  })
})

describe('bulkMove', () => {
  function seq(...names: string[]): TreeValue[] {
    return [{ type: 'section', name: 'S', entries: names.map((name) => ({ type: 'entries', name, entries: [] })) }]
  }
  function names(data: TreeValue[]): string[] {
    return node(data[0]).entries!.map((e) => node(e).name!)
  }

  it('moves a block of siblings up', () => {
    const data = seq('A', 'B', 'C', 'D')
    const r = bulkMove(
      data,
      [
        [0, 'entries', 1],
        [0, 'entries', 2],
      ],
      -1,
    )
    expect(names(r.data)).toEqual(['B', 'C', 'A', 'D'])
  })

  it('moves a block of siblings down', () => {
    const data = seq('A', 'B', 'C', 'D')
    const r = bulkMove(
      data,
      [
        [0, 'entries', 1],
        [0, 'entries', 2],
      ],
      1,
    )
    expect(names(r.data)).toEqual(['A', 'D', 'B', 'C'])
  })

  it('is a no-op moving up at the top', () => {
    const data = seq('A', 'B')
    const r = bulkMove(
      data,
      [
        [0, 'entries', 0],
        [0, 'entries', 1],
      ],
      -1,
    )
    expect(names(r.data)).toEqual(['A', 'B'])
  })

  it('is a no-op moving down at the bottom', () => {
    const data = seq('A', 'B')
    const r = bulkMove(
      data,
      [
        [0, 'entries', 0],
        [0, 'entries', 1],
      ],
      1,
    )
    expect(names(r.data)).toEqual(['A', 'B'])
  })

  it('moves top-level sections up and down', () => {
    const up = bulkMove(makeTestData(), [[1]], -1)
    expect(node(up.data[0]).name).toBe('Chapter 2')
    const down = bulkMove(makeTestData(), [[0]], 1)
    expect(node(down.data[0]).name).toBe('Chapter 2')
  })

  it('preserves non-selected siblings', () => {
    const data = seq('A', 'B', 'C', 'D', 'E')
    const r = bulkMove(data, [[0, 'entries', 2]], 1)
    expect(names(r.data)).toEqual(['A', 'B', 'D', 'C', 'E'])
  })
})

describe('bulkDelete', () => {
  it('deletes multiple siblings', () => {
    const data = makeTestData()
    const result = bulkDelete(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    expect(node(result[0]).entries).toEqual(['Para 1'])
  })

  it('deletes top-level sections', () => {
    const data = makeTestData()
    const result = bulkDelete(data, [[0], [1]])
    expect(result).toHaveLength(0)
  })

  it('preserves unselected siblings', () => {
    const data: TreeValue[] = [
      {
        type: 'section',
        name: 'S',
        entries: ['A', 'B', 'C', 'D'].map((name) => ({ type: 'entries', name, entries: [] })),
      },
    ]
    const result = bulkDelete(data, [
      [0, 'entries', 1],
      [0, 'entries', 3],
    ])
    const entries = node(result[0]).entries!
    expect(entries.map((e) => node(e).name)).toEqual(['A', 'C'])
  })
})

describe('bulkDissolve', () => {
  it('dissolves multiple nodes, splicing children in place', () => {
    const data = makeTestData()
    const result = bulkDissolve(data, [
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    expect(node(result[0]).entries).toEqual(['Para 1', 'Room A text.', 'Room B text.'])
  })

  it('skips string entries', () => {
    const data = makeTestData()
    const originalLen = node(data[0]).entries!.length
    const result = bulkDissolve(data, [[0, 'entries', 0]])
    expect(node(result[0]).entries).toHaveLength(originalLen)
  })
})

describe('flags', () => {
  it('adds a flag to an unflagged node', () => {
    const data = makeTestData()
    expect(getNodeFlags(node(data[0]).entries![1])).toEqual([])
    const result = toggleFlag(data, [0, 'entries', 1], '1e')
    expect(getNodeFlags(node(result[0]).entries![1])).toEqual(['1e'])
  })

  it('supports multiple flags on the same node', () => {
    const data = makeTestData()
    const once = toggleFlag(data, [0], '1e')
    const twice = toggleFlag(once, [0], 'review')
    expect(getNodeFlags(twice[0])).toEqual(['1e', 'review'])
  })

  it('toggles a flag off', () => {
    const data = makeTestData()
    const withBoth = toggleFlag(toggleFlag(data, [0], '1e'), [0], 'review')
    const withOneOff = toggleFlag(withBoth, [0], '1e')
    expect(getNodeFlags(withOneOff[0])).toEqual(['review'])
  })

  it('removes the _flags property once the last flag is toggled off', () => {
    const data = makeTestData()
    const flagged = toggleFlag(data, [0], '1e')
    const unflagged = toggleFlag(flagged, [0], '1e')
    expect((unflagged[0] as BlockNode)._flags).toBeUndefined()
  })

  it('bulk-flags multiple nodes', () => {
    const data = makeTestData()
    const result = bulkFlag(
      data,
      [
        [0, 'entries', 1],
        [0, 'entries', 2],
      ],
      '1e',
    )
    const entries = node(result[0]).entries!
    expect(getNodeFlags(entries[1])).toEqual(['1e'])
    expect(getNodeFlags(entries[2])).toEqual(['1e'])
  })

  it('bulk-clears flags from multiple nodes', () => {
    const data = makeTestData()
    const flagged = bulkFlag(
      data,
      [
        [0, 'entries', 1],
        [0, 'entries', 2],
      ],
      '1e',
    )
    const cleared = bulkClearFlags(flagged, [
      [0, 'entries', 1],
      [0, 'entries', 2],
    ])
    const entries = node(cleared[0]).entries!
    expect(getNodeFlags(entries[1])).toEqual([])
    expect(getNodeFlags(entries[2])).toEqual([])
  })

  it('counts all flagged nodes anywhere in the tree', () => {
    const data = makeTestData()
    node(data[0])._flags = ['1e']
    node(node(data[0]).entries![1])._flags = ['review']
    expect(countFlagged(data)).toBe(2)
  })
})
