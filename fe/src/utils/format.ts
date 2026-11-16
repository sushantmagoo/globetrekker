import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

export const PUBLIC_APP_URL: string =
  import.meta.env.VITE_PUBLIC_APP_URL ?? (typeof window !== 'undefined' ? window.location.origin : '')

export function fromNow(iso: string | null | undefined): string {
  return iso ? dayjs(iso).fromNow() : ''
}

export function longDate(iso: string | null | undefined): string {
  return iso ? dayjs(iso).format('D MMM YYYY') : ''
}

/** "3–9 Apr 2026", "28 Mar – 2 Apr 2026", "30 Dec 2025 – 4 Jan 2026" */
export function travelRange(start: string | null, end: string | null): string {
  if (!start && !end) return ''
  if (!start || !end || start === end) return dayjs(start ?? end).format('D MMM YYYY')
  const s = dayjs(start)
  const e = dayjs(end)
  if (s.year() !== e.year()) return `${s.format('D MMM YYYY')} – ${e.format('D MMM YYYY')}`
  if (s.month() !== e.month()) return `${s.format('D MMM')} – ${e.format('D MMM YYYY')}`
  return `${s.format('D')}–${e.format('D MMM YYYY')}`
}

export function journalUrl(slug: string, shareToken?: string | null): string {
  const base = `${PUBLIC_APP_URL}/j/${slug}`
  return shareToken ? `${base}?t=${encodeURIComponent(shareToken)}` : base
}

export function pluralize(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}
