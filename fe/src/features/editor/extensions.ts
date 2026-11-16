import Highlight from '@tiptap/extension-highlight'
import TextAlign from '@tiptap/extension-text-align'
import Typography from '@tiptap/extension-typography'
import { CharacterCount, Placeholder } from '@tiptap/extensions'
import StarterKit from '@tiptap/starter-kit'
import { VideoEmbed } from './videoEmbed'

/** The set of nodes/marks the backend renderer accepts (be/app/content/render.py). */
export const editorExtensions = [
  StarterKit.configure({
    heading: { levels: [2, 3] },
    link: {
      openOnClick: false,
      autolink: true,
      protocols: ['http', 'https', 'mailto'],
      HTMLAttributes: { rel: 'noopener nofollow ugc', target: '_blank' },
    },
  }),
  Highlight,
  TextAlign.configure({ types: ['heading', 'paragraph'], alignments: ['left', 'center', 'right', 'justify'] }),
  Typography,
  Placeholder.configure({ placeholder: 'Tell the story of your trip…' }),
  CharacterCount,
  VideoEmbed,
]
