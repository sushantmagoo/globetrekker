import { describe, expect, it } from 'vitest'
import { normalizeVideoUrl } from './videoEmbed'

describe('normalizeVideoUrl (must match backend render.normalize_video_url)', () => {
  it.each([
    ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'],
    ['https://youtu.be/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'],
    ['https://m.youtube.com/shorts/dQw4w9WgXcQ', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'],
    ['https://vimeo.com/76979871', 'https://player.vimeo.com/video/76979871'],
    ['https://player.vimeo.com/video/76979871', 'https://player.vimeo.com/video/76979871'],
  ])('%s', (input, expected) => {
    expect(normalizeVideoUrl(input)).toBe(expected)
  })

  it.each(['javascript:alert(1)', 'https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ', 'not a url', 'https://vimeo.com/abc'])(
    'rejects %s',
    (input) => {
      expect(normalizeVideoUrl(input)).toBeNull()
    },
  )
})
