// Mirrors be/app/schemas. Keep in sync with the backend OpenAPI schema.
import type { JSONContent } from '@tiptap/core'

export type Visibility = 'public' | 'followers' | 'unlisted' | 'private'
export type JournalStatus = 'draft' | 'published'
export type NotificationType = 'follow' | 'like' | 'comment' | 'reply'

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

export interface TokenOut {
  access_token: string
  token_type: string
  expires_in: number
}

export interface UserSummary {
  id: string
  username: string
  display_name: string
}

export interface Profile extends UserSummary {
  bio: string | null
  home_country: string | null
  website_url: string | null
  follower_count: number
  following_count: number
  journal_count: number
  created_at: string
  is_following: boolean
  is_me: boolean
}

export interface Me extends Profile {
  email: string
  default_visibility: Visibility
  role: string
}

export interface Location {
  place_name: string
  country_code: string | null
  lat: number
  lng: number
}

export interface JournalCard {
  id: string
  slug: string
  title: string
  subtitle: string | null
  excerpt: string
  author: UserSummary
  status: JournalStatus
  visibility: Visibility
  place_name: string | null
  country_code: string | null
  lat: number | null
  lng: number | null
  travel_start: string | null
  travel_end: string | null
  reading_minutes: number
  like_count: number
  comment_count: number
  tags: string[]
  published_at: string | null
  updated_at: string
  liked_by_me: boolean
  bookmarked_by_me: boolean
}

export interface JournalDetail extends JournalCard {
  content_html: string
  word_count: number
  is_owner: boolean
  share_token: string | null
}

/** TipTap/ProseMirror document JSON (the canonical journal format). */
export type ProseMirrorDoc = JSONContent & { type: 'doc' }

export interface JournalEdit extends JournalDetail {
  content_json: ProseMirrorDoc
  version: number
}

export interface JournalUpdate {
  version: number
  title?: string
  subtitle?: string | null
  content_json?: ProseMirrorDoc
  visibility?: Visibility
  location?: Location | null
  clear_location?: boolean
  travel_start?: string | null
  travel_end?: string | null
  tags?: string[]
}

export interface Comment {
  id: string
  journal_id: string
  parent_id: string | null
  author: UserSummary
  body: string
  created_at: string
  edited_at: string | null
  replies: Comment[]
  can_delete: boolean
  can_edit: boolean
}

export interface Notification {
  id: string
  type: NotificationType
  actor: UserSummary
  journal_slug: string | null
  journal_title: string | null
  comment_id: string | null
  read_at: string | null
  created_at: string
}

export interface FieldError {
  field: string
  message: string
}
