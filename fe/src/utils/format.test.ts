import { describe, expect, it } from 'vitest'
import { flag } from './countries'
import { travelRange } from './format'

describe('travelRange', () => {
  it('handles same month, different months and different years', () => {
    expect(travelRange('2026-04-03', '2026-04-09')).toBe('3–9 Apr 2026')
    expect(travelRange('2026-03-28', '2026-04-02')).toBe('28 Mar – 2 Apr 2026')
    expect(travelRange('2025-12-30', '2026-01-04')).toBe('30 Dec 2025 – 4 Jan 2026')
  })

  it('handles single or missing dates', () => {
    expect(travelRange(null, null)).toBe('')
    expect(travelRange('2026-04-03', null)).toBe('3 Apr 2026')
    expect(travelRange('2026-04-03', '2026-04-03')).toBe('3 Apr 2026')
  })
})

describe('flag', () => {
  it('builds regional indicator emoji', () => {
    expect(flag('jp')).toBe('🇯🇵')
    expect(flag(null)).toBe('')
  })
})
