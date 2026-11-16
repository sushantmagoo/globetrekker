import DOMPurify from 'dompurify'

const ALLOWED_IFRAME_PREFIXES = [
  'https://www.youtube-nocookie.com/embed/',
  'https://player.vimeo.com/video/',
]

// Defence in depth: the server already sanitises journal HTML. Here we additionally
// only keep iframes that point at the two allowed video players.
DOMPurify.addHook('uponSanitizeElement', (node, data) => {
  if (data.tagName === 'iframe') {
    const src = (node as Element).getAttribute('src') ?? ''
    if (!ALLOWED_IFRAME_PREFIXES.some((p) => src.startsWith(p))) {
      node.parentNode?.removeChild(node)
    }
  }
})

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener nofollow ugc')
  }
})

export function sanitizeJournalHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ADD_TAGS: ['iframe'],
    ADD_ATTR: ['allow', 'allowfullscreen', 'loading', 'referrerpolicy', 'target'],
    FORBID_TAGS: ['img', 'style', 'form', 'input'],
  })
}
