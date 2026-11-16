import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, NetworkError } from '../../api/client'
import type { JournalEdit, JournalUpdate } from '../../api/types'

export type SaveStatus = 'saved' | 'dirty' | 'saving' | 'offline' | 'error' | 'conflict'
export type Changes = Omit<JournalUpdate, 'version'>

const DEBOUNCE_MS = 2000
const MAX_RETRY_MS = 30_000

interface LocalDraft {
  changes: Changes
  savedAt: number
  baseVersion: number
}

export const localDraftKey = (id: string) => `gt:draft:${id}`

export function readLocalDraft(id: string): LocalDraft | null {
  try {
    const raw = localStorage.getItem(localDraftKey(id))
    return raw ? (JSON.parse(raw) as LocalDraft) : null
  } catch {
    return null
  }
}

function writeLocalDraft(id: string, draft: LocalDraft | null) {
  try {
    if (draft) localStorage.setItem(localDraftKey(id), JSON.stringify(draft))
    else localStorage.removeItem(localDraftKey(id))
  } catch {
    /* storage full or unavailable: autosave still works */
  }
}

interface Options {
  journalId: string
  initialVersion: number
  save: (id: string, data: JournalUpdate) => Promise<JournalEdit>
  onSaved: (journal: JournalEdit) => void
}

/**
 * Debounced, ordered autosave with optimistic concurrency.
 * - Changes accumulate in `pending` and are sent 2 s after the last edit.
 * - Only one request is in flight; edits made meanwhile are sent right after.
 * - Network failures retry with backoff; a 409 stops saving and reports a conflict.
 * - Unsaved changes are mirrored to localStorage for crash recovery.
 */
export function useAutosave({ journalId, initialVersion, save, onSaved }: Options) {
  const [status, setStatus] = useState<SaveStatus>('saved')
  const [lastError, setLastError] = useState<string | null>(null)
  const version = useRef(initialVersion)
  const pending = useRef<Changes>({})
  const inFlight = useRef<Promise<void> | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryDelay = useRef(2000)
  const stopped = useRef(false)

  const hasPending = () => Object.keys(pending.current).length > 0

  const flush = useCallback(async function flushPending(): Promise<void> {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
    if (stopped.current) return
    if (inFlight.current) {
      await inFlight.current
      return hasPending() ? flushPending() : undefined
    }
    if (!hasPending()) return

    const sending = pending.current
    pending.current = {}
    setStatus('saving')

    const run = (async () => {
      try {
        const saved = await save(journalId, { ...sending, version: version.current })
        version.current = saved.version
        retryDelay.current = 2000
        setLastError(null)
        onSaved(saved)
        if (hasPending()) {
          setStatus('dirty')
        } else {
          setStatus('saved')
          writeLocalDraft(journalId, null)
        }
      } catch (err) {
        // Put the unsent changes back underneath anything typed since.
        pending.current = { ...sending, ...pending.current }
        if (err instanceof ApiError && err.status === 409) {
          stopped.current = true
          setStatus('conflict')
        } else if (err instanceof NetworkError || (err instanceof ApiError && err.status >= 500)) {
          setStatus('offline')
          timer.current = setTimeout(() => void flushPending(), retryDelay.current)
          retryDelay.current = Math.min(retryDelay.current * 2, MAX_RETRY_MS)
        } else {
          setStatus('error')
          setLastError(err instanceof Error ? err.message : 'Could not save')
        }
      }
    })()
    inFlight.current = run
    await run
    inFlight.current = null
    if (hasPending() && !stopped.current && !timer.current) await flushPending()
  }, [journalId, save, onSaved])

  const update = useCallback(
    (changes: Changes) => {
      if (stopped.current) return
      pending.current = { ...pending.current, ...changes }
      setStatus((s) => (s === 'saving' ? s : 'dirty'))
      writeLocalDraft(journalId, {
        changes: pending.current,
        savedAt: Date.now(),
        baseVersion: version.current,
      })
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => void flush(), DEBOUNCE_MS)
    },
    [journalId, flush],
  )

  /** Call when another action (publish, …) bumped the version server-side. */
  const setVersion = useCallback((v: number) => {
    version.current = v
  }, [])

  // Save on tab hide / warn before leaving with unsaved changes.
  useEffect(() => {
    const onHide = () => {
      if (document.visibilityState === 'hidden' && hasPending()) void flush()
    }
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasPending() || inFlight.current) e.preventDefault()
    }
    document.addEventListener('visibilitychange', onHide)
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => {
      document.removeEventListener('visibilitychange', onHide)
      window.removeEventListener('beforeunload', onBeforeUnload)
      if (timer.current) clearTimeout(timer.current)
    }
  }, [flush])

  return { status, lastError, update, flush, setVersion }
}
