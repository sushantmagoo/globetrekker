import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, NetworkError } from '../../api/client'
import type { JournalEdit, JournalUpdate } from '../../api/types'
import { localDraftKey, useAutosave } from './useAutosave'

const saved = (version: number) => ({ id: 'j1', version }) as JournalEdit

function setup(save: (id: string, data: JournalUpdate) => Promise<JournalEdit>) {
  const onSaved = vi.fn()
  const hook = renderHook(() => useAutosave({ journalId: 'j1', initialVersion: 1, save, onSaved }))
  return { ...hook, onSaved }
}

describe('useAutosave', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
  })
  afterEach(() => vi.useRealTimers())

  it('debounces edits into one request with the current version', async () => {
    const save = vi.fn().mockResolvedValue(saved(2))
    const { result, onSaved } = setup(save)

    act(() => {
      result.current.update({ title: 'Kyo' })
      result.current.update({ title: 'Kyoto' })
    })
    expect(result.current.status).toBe('dirty')
    expect(localStorage.getItem(localDraftKey('j1'))).toContain('Kyoto')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(save).toHaveBeenCalledTimes(1)
    expect(save).toHaveBeenCalledWith('j1', { title: 'Kyoto', version: 1 })
    expect(onSaved).toHaveBeenCalled()
    expect(result.current.status).toBe('saved')
    expect(localStorage.getItem(localDraftKey('j1'))).toBeNull()
  })

  it('uses the new version for the next save', async () => {
    const save = vi.fn().mockResolvedValueOnce(saved(2)).mockResolvedValueOnce(saved(3))
    const { result } = setup(save)
    act(() => result.current.update({ title: 'A' }))
    await act(() => result.current.flush())
    act(() => result.current.update({ title: 'B' }))
    await act(() => result.current.flush())
    expect(save.mock.calls[1][1]).toEqual({ title: 'B', version: 2 })
  })

  it('keeps changes and retries when offline', async () => {
    const save = vi.fn().mockRejectedValueOnce(new NetworkError('offline')).mockResolvedValueOnce(saved(2))
    const { result } = setup(save)
    act(() => result.current.update({ subtitle: 'x' }))
    await act(() => result.current.flush())
    expect(result.current.status).toBe('offline')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(save).toHaveBeenCalledTimes(2)
    expect(save.mock.calls[1][1]).toEqual({ subtitle: 'x', version: 1 })
    expect(result.current.status).toBe('saved')
  })

  it('stops on a version conflict and keeps the local copy', async () => {
    const save = vi.fn().mockRejectedValue(new ApiError(409, { title: 'Conflict' }))
    const { result } = setup(save)
    act(() => result.current.update({ title: 'mine' }))
    await act(() => result.current.flush())
    expect(result.current.status).toBe('conflict')
    expect(localStorage.getItem(localDraftKey('j1'))).toContain('mine')

    act(() => result.current.update({ title: 'more' }))
    await act(() => result.current.flush())
    expect(save).toHaveBeenCalledTimes(1)
  })
})
