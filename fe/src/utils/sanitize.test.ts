import { describe, expect, it } from 'vitest'
import { avatarColor, initials } from '../components/UserAvatar'
import { shareLink } from '../components/ShareModal'
import { sanitizeJournalHtml } from './sanitize'

describe('sanitizeJournalHtml', () => {
  it('keeps formatting and allowed video iframes', () => {
    const html =
      '<h2>Day</h2><p><strong>b</strong> <mark>m</mark></p><div class="video-embed"><iframe src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"></iframe></div>'
    const out = sanitizeJournalHtml(html)
    expect(out).toContain('<h2>Day</h2>')
    expect(out).toContain('<mark>m</mark>')
    expect(out).toContain('src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ"')
  })

  it('drops scripts, images, event handlers and foreign iframes', () => {
    const out = sanitizeJournalHtml(
      '<p onclick="x()">hi</p><script>alert(1)</script><img src="x" onerror="y()"><iframe src="https://evil.example/x"></iframe>',
    )
    expect(out).toBe('<p>hi</p>')
  })

  it('opens links in a new tab with safe rel', () => {
    const out = sanitizeJournalHtml('<p><a href="https://example.com">x</a> <a href="javascript:alert(1)">y</a></p>')
    expect(out).toContain('href="https://example.com"')
    expect(out).toContain('target="_blank"')
    expect(out).toContain('rel="noopener nofollow ugc"')
    expect(out).not.toContain('javascript:')
  })
})

describe('shareLink', () => {
  it('only adds the token for unlisted journals', () => {
    expect(shareLink('kyoto-abc123', 'public', 'tok')).toMatch(/\/j\/kyoto-abc123$/)
    expect(shareLink('kyoto-abc123', 'unlisted', 'tok')).toMatch(/\/j\/kyoto-abc123\?t=tok$/)
    expect(shareLink('kyoto-abc123', 'private', 'tok')).not.toContain('?t=')
  })
})

describe('avatar helpers', () => {
  it('builds initials from names', () => {
    expect(initials('Maya Explorer')).toBe('ME')
    expect(initials('Ana Maria de Souza')).toBe('AS')
    expect(initials('cher')).toBe('CH')
  })

  it('gives each username a stable colour', () => {
    expect(avatarColor('maya')).toBe(avatarColor('maya'))
    expect(avatarColor('maya')).toMatch(/^#[0-9a-f]{6}$/)
  })
})
