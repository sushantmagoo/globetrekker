import type { Visibility } from '../api/types'

export const VISIBILITY_OPTIONS: { value: Visibility; label: string; hint: string }[] = [
  { value: 'public', label: 'Public', hint: 'Anyone can read it; shown in feeds and Explore' },
  { value: 'followers', label: 'Followers', hint: 'Only people who follow you' },
  { value: 'unlisted', label: 'Unlisted', hint: 'Anyone with the link; not listed anywhere' },
  { value: 'private', label: 'Private', hint: 'Only you' },
]
