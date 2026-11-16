import { Node, mergeAttributes } from '@tiptap/core'

const YT_ID = /^[A-Za-z0-9_-]{11}$/
const VIMEO_ID = /^\d{6,12}$/

/** Mirrors backend `normalize_video_url`: returns a privacy-friendly embed URL or null. */
export function normalizeVideoUrl(raw: string): string | null {
  let u: URL
  try {
    u = new URL(raw.trim())
  } catch {
    return null
  }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null
  const host = u.hostname.toLowerCase().replace(/^www\./, '').replace(/^m\./, '')
  let id: string | null | undefined = null
  if (host === 'youtube.com' || host === 'youtube-nocookie.com') {
    if (u.pathname === '/watch') id = u.searchParams.get('v')
    else if (/^\/(embed|shorts|live)\//.test(u.pathname)) id = u.pathname.split('/')[2]
    if (id && YT_ID.test(id)) return `https://www.youtube-nocookie.com/embed/${id}`
  } else if (host === 'youtu.be') {
    id = u.pathname.slice(1).split('/')[0]
    if (YT_ID.test(id)) return `https://www.youtube-nocookie.com/embed/${id}`
  } else if (host === 'vimeo.com' || host === 'player.vimeo.com') {
    id = u.pathname.split('/').filter(Boolean).pop()
    if (id && VIMEO_ID.test(id)) return `https://player.vimeo.com/video/${id}`
  }
  return null
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    videoEmbed: {
      setVideoEmbed: (options: { src: string }) => ReturnType
    }
  }
}

export const VideoEmbed = Node.create({
  name: 'videoEmbed',
  group: 'block',
  atom: true,
  draggable: true,

  addAttributes() {
    return { src: { default: null } }
  },

  parseHTML() {
    return [
      {
        tag: 'iframe[src]',
        getAttrs: (el) => {
          const src = normalizeVideoUrl((el as HTMLElement).getAttribute('src') ?? '')
          return src ? { src } : false
        },
      },
    ]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      { class: 'video-embed' },
      [
        'iframe',
        mergeAttributes(HTMLAttributes, {
          title: 'Embedded video',
          loading: 'lazy',
          allow: 'encrypted-media; picture-in-picture; fullscreen',
          allowfullscreen: 'true',
          referrerpolicy: 'strict-origin-when-cross-origin',
        }),
      ],
    ]
  },

  addCommands() {
    return {
      setVideoEmbed:
        ({ src }) =>
        ({ commands }) => {
          const normalized = normalizeVideoUrl(src)
          if (!normalized) return false
          return commands.insertContent({ type: this.name, attrs: { src: normalized } })
        },
    }
  },
})
