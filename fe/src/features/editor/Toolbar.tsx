import {
  AlignCenterOutlined,
  AlignLeftOutlined,
  AlignRightOutlined,
  BoldOutlined,
  CodeOutlined,
  HighlightOutlined,
  ItalicOutlined,
  LinkOutlined,
  MinusOutlined,
  OrderedListOutlined,
  RedoOutlined,
  StrikethroughOutlined,
  UnderlineOutlined,
  UndoOutlined,
  UnorderedListOutlined,
  YoutubeOutlined,
} from '@ant-design/icons'
import type { Editor } from '@tiptap/react'
import { useEditorState } from '@tiptap/react'
import { App, Button, Divider, Form, Input, Modal, Select, Tooltip } from 'antd'
import { useState, type ReactNode } from 'react'
import { normalizeVideoUrl } from './videoEmbed'

function ToolButton({
  label,
  icon,
  active,
  disabled,
  onClick,
}: {
  label: string
  icon: ReactNode
  active?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <Tooltip title={label} mouseEnterDelay={0.4}>
      <Button
        type={active ? 'primary' : 'text'}
        ghost={active}
        size="small"
        icon={icon}
        aria-label={label}
        aria-pressed={active}
        disabled={disabled}
        onMouseDown={(e) => e.preventDefault()} // keep the editor selection
        onClick={onClick}
      />
    </Tooltip>
  )
}

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const mod = isMac ? '⌘' : 'Ctrl'

export function Toolbar({ editor }: { editor: Editor }) {
  const { message } = App.useApp()
  const [linkOpen, setLinkOpen] = useState(false)
  const [videoOpen, setVideoOpen] = useState(false)
  const [linkForm] = Form.useForm<{ href: string }>()
  const [videoForm] = Form.useForm<{ url: string }>()

  const s = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive('bold'),
      italic: e.isActive('italic'),
      underline: e.isActive('underline'),
      strike: e.isActive('strike'),
      highlight: e.isActive('highlight'),
      code: e.isActive('code'),
      link: e.isActive('link'),
      bullet: e.isActive('bulletList'),
      ordered: e.isActive('orderedList'),
      quote: e.isActive('blockquote'),
      h2: e.isActive('heading', { level: 2 }),
      h3: e.isActive('heading', { level: 3 }),
      center: e.isActive({ textAlign: 'center' }),
      right: e.isActive({ textAlign: 'right' }),
      canUndo: e.can().undo(),
      canRedo: e.can().redo(),
    }),
  })

  const chain = () => editor.chain().focus()
  const block = s.h2 ? 'h2' : s.h3 ? 'h3' : 'p'

  const openLink = () => {
    linkForm.setFieldsValue({ href: editor.getAttributes('link').href ?? '' })
    setLinkOpen(true)
  }
  const applyLink = ({ href }: { href: string }) => {
    const value = href.trim()
    if (!value) chain().extendMarkRange('link').unsetLink().run()
    else {
      const withScheme = /^(https?:|mailto:)/i.test(value) ? value : `https://${value}`
      chain().extendMarkRange('link').setLink({ href: withScheme }).run()
    }
    setLinkOpen(false)
  }
  const applyVideo = ({ url }: { url: string }) => {
    if (!chain().setVideoEmbed({ src: url }).run()) {
      message.error('Paste a YouTube or Vimeo link')
      return
    }
    videoForm.resetFields()
    setVideoOpen(false)
  }

  return (
    <div className="editor-toolbar" role="toolbar" aria-label="Formatting">
      <Select
        size="small"
        value={block}
        style={{ width: 120 }}
        aria-label="Text style"
        onChange={(v) => {
          if (v === 'p') chain().setParagraph().run()
          else chain().toggleHeading({ level: v === 'h2' ? 2 : 3 }).run()
        }}
        options={[
          { value: 'p', label: 'Paragraph' },
          { value: 'h2', label: 'Heading' },
          { value: 'h3', label: 'Subheading' },
        ]}
      />
      <Divider orientation="vertical" />
      <ToolButton label={`Bold (${mod}+B)`} icon={<BoldOutlined />} active={s.bold} onClick={() => chain().toggleBold().run()} />
      <ToolButton label={`Italic (${mod}+I)`} icon={<ItalicOutlined />} active={s.italic} onClick={() => chain().toggleItalic().run()} />
      <ToolButton label={`Underline (${mod}+U)`} icon={<UnderlineOutlined />} active={s.underline} onClick={() => chain().toggleUnderline().run()} />
      <ToolButton label="Strikethrough" icon={<StrikethroughOutlined />} active={s.strike} onClick={() => chain().toggleStrike().run()} />
      <ToolButton label="Highlight" icon={<HighlightOutlined />} active={s.highlight} onClick={() => chain().toggleHighlight().run()} />
      <ToolButton label="Inline code" icon={<CodeOutlined />} active={s.code} onClick={() => chain().toggleCode().run()} />
      <ToolButton label="Link" icon={<LinkOutlined />} active={s.link} onClick={openLink} />
      <Divider orientation="vertical" />
      <ToolButton label="Bulleted list" icon={<UnorderedListOutlined />} active={s.bullet} onClick={() => chain().toggleBulletList().run()} />
      <ToolButton label="Numbered list" icon={<OrderedListOutlined />} active={s.ordered} onClick={() => chain().toggleOrderedList().run()} />
      <ToolButton label="Quote" icon={<span className="quote-icon">❝</span>} active={s.quote} onClick={() => chain().toggleBlockquote().run()} />
      <ToolButton label="Divider" icon={<MinusOutlined />} onClick={() => chain().setHorizontalRule().run()} />
      <ToolButton label="Embed YouTube or Vimeo video" icon={<YoutubeOutlined />} onClick={() => setVideoOpen(true)} />
      <Divider orientation="vertical" />
      <ToolButton label="Align left" icon={<AlignLeftOutlined />} active={!s.center && !s.right} onClick={() => chain().setTextAlign('left').run()} />
      <ToolButton label="Align center" icon={<AlignCenterOutlined />} active={s.center} onClick={() => chain().setTextAlign('center').run()} />
      <ToolButton label="Align right" icon={<AlignRightOutlined />} active={s.right} onClick={() => chain().setTextAlign('right').run()} />
      <Divider orientation="vertical" />
      <ToolButton label={`Undo (${mod}+Z)`} icon={<UndoOutlined />} disabled={!s.canUndo} onClick={() => chain().undo().run()} />
      <ToolButton label={`Redo (${mod}+Shift+Z)`} icon={<RedoOutlined />} disabled={!s.canRedo} onClick={() => chain().redo().run()} />

      <Modal title="Link" open={linkOpen} onCancel={() => setLinkOpen(false)} onOk={() => linkForm.submit()} okText="Apply" destroyOnHidden>
        <Form form={linkForm} onFinish={applyLink} layout="vertical">
          <Form.Item name="href" label="URL" extra="Leave empty to remove the link.">
            <Input placeholder="https://example.com" autoFocus />
          </Form.Item>
        </Form>
      </Modal>
      <Modal title="Embed a video" open={videoOpen} onCancel={() => setVideoOpen(false)} onOk={() => videoForm.submit()} okText="Embed" destroyOnHidden>
        <Form form={videoForm} onFinish={applyVideo} layout="vertical">
          <Form.Item
            name="url"
            label="YouTube or Vimeo link"
            rules={[
              { required: true, message: 'Paste a link' },
              {
                validator: (_, v: string) =>
                  !v || normalizeVideoUrl(v) ? Promise.resolve() : Promise.reject(new Error('Only YouTube and Vimeo links are supported')),
              },
            ]}
          >
            <Input placeholder="https://www.youtube.com/watch?v=…" autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
