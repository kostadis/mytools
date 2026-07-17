import { defineConfig } from 'vitest/config'

// Pure logic modules only (lib/*.ts) — no DOM needed, so plain node env.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
