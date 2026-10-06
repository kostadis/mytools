import { expect, mock, test } from 'claude-code/testing'

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the empty pane draws on ${surface}`, async ($, on) => {
    mock.clock(on)
    const ui = await $.ui.mount({ plugin: 'jobs', surface, component: 'Pane', requestId: 'jobs', props: { title: 'Jobs' } } as never)
    expect(JSON.stringify(await ui.drawn())).toContain('No background work yet.')
  })
}

test('a background shell appears in the pane as running', async ($, on) => {
  mock.clock(on)
  on('ui.open', () => ({ value: { isShown: true, isPlaced: true } }) as never)
  on('ui.status', () => ({ value: undefined }) as never)
  on('tool.call', () => ({ result: { backgroundTaskId: 'b1', stdout: '', stderr: '', interrupted: false } }) as never)
  await $.tool.call({ tool: 'Bash', command: 'enhance_summary ch52', description: 'Enhance ch52 summary', run_in_background: true } as never)
  const ui = await $.ui.mount({ plugin: 'jobs', surface: 'terminal', component: 'Pane', requestId: 'jobs', props: { title: 'Jobs' } } as never)
  const drawn = JSON.stringify(await ui.drawn())
  expect(drawn).toContain('Running (1)')
  expect(drawn).toContain('Enhance ch52 summary')
})
