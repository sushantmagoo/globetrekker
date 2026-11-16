import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloudSyncOutlined,
  DeleteOutlined,
  DisconnectOutlined,
  EditOutlined,
  EnvironmentOutlined,
  EyeOutlined,
  ShareAltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { EditorContent, useEditor } from '@tiptap/react'
import { BubbleMenu } from '@tiptap/react/menus'
import {
  Alert,
  App,
  Button,
  DatePicker,
  Form,
  Input,
  Result,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd'
import dayjs, { type Dayjs } from 'dayjs'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import { journals } from '../../api/endpoints'
import type { JournalEdit, Location, ProseMirrorDoc, Visibility } from '../../api/types'
import { FullPageSpin } from '../../components/RequireAuth'
import { ShareModal, shareLink, tryNativeShare } from '../../components/ShareModal'
import { flag } from '../../utils/countries'
import { sanitizeJournalHtml } from '../../utils/sanitize'
import { VISIBILITY_OPTIONS } from '../../utils/visibility'
import { editorExtensions } from './extensions'
import { LocationModal } from './LocationModal'
import { Toolbar } from './Toolbar'
import { readLocalDraft, useAutosave, type Changes, type SaveStatus } from './useAutosave'

function SaveIndicator({ status, error }: { status: SaveStatus; error: string | null }) {
  const map: Record<SaveStatus, { icon: React.ReactNode; text: string; type?: 'secondary' | 'warning' | 'danger' }> = {
    saved: { icon: <CheckCircleOutlined />, text: 'Saved', type: 'secondary' },
    dirty: { icon: <EditOutlined />, text: 'Unsaved changes', type: 'secondary' },
    saving: { icon: <CloudSyncOutlined />, text: 'Saving…', type: 'secondary' },
    offline: { icon: <DisconnectOutlined />, text: 'Offline, will retry', type: 'warning' },
    error: { icon: <WarningOutlined />, text: error ?? 'Could not save', type: 'danger' },
    conflict: { icon: <WarningOutlined />, text: 'Edited elsewhere', type: 'danger' },
  }
  const m = map[status]
  return (
    <Typography.Text type={m.type} className="save-indicator" aria-live="polite">
      {m.icon} {m.text}
    </Typography.Text>
  )
}

export default function EditorPage() {
  const { id = '' } = useParams()
  const query = useQuery({
    queryKey: ['journal-edit', id],
    queryFn: () => journals.getForEdit(id),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })

  if (query.isPending) return <FullPageSpin />
  if (query.isError) {
    const notFound = query.error instanceof ApiError && query.error.status === 404
    return (
      <Result
        status={notFound ? '404' : 'error'}
        title={notFound ? 'Journal not found' : 'Could not load journal'}
        subTitle={notFound ? undefined : errorMessage(query.error)}
        extra={<Link to="/me/drafts">Back to drafts</Link>}
      />
    )
  }
  return <JournalEditor key={id} initial={query.data} />
}

function JournalEditor({ initial }: { initial: JournalEdit }) {
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [journal, setJournal] = useState(initial)
  const [title, setTitle] = useState(initial.title)
  const [subtitle, setSubtitle] = useState(initial.subtitle ?? '')
  const [visibility, setVisibility] = useState<Visibility>(initial.visibility)
  const [tags, setTags] = useState<string[]>(initial.tags)
  const [dates, setDates] = useState<[Dayjs | null, Dayjs | null] | null>(
    initial.travel_start || initial.travel_end
      ? [initial.travel_start ? dayjs(initial.travel_start) : null, initial.travel_end ? dayjs(initial.travel_end) : null]
      : null,
  )
  const [location, setLocation] = useState<Location | null>(
    initial.lat != null && initial.lng != null && initial.place_name
      ? { place_name: initial.place_name, country_code: initial.country_code, lat: initial.lat, lng: initial.lng }
      : null,
  )
  const [locationOpen, setLocationOpen] = useState(false)
  const [shareOpen, setShareOpen] = useState(false)
  const [preview, setPreview] = useState(false)
  const [busy, setBusy] = useState<'publish' | 'unpublish' | 'delete' | null>(null)
  const [publishErrors, setPublishErrors] = useState<string[]>([])

  const onSaved = useCallback((saved: JournalEdit) => setJournal(saved), [])
  const autosave = useAutosave({
    journalId: initial.id,
    initialVersion: initial.version,
    save: journals.update,
    onSaved,
  })
  const { update } = autosave

  const editor = useEditor({
    extensions: editorExtensions,
    // An empty doc has no blocks; let TipTap create its default empty paragraph (needed for the placeholder).
    content: initial.content_json.content?.length ? (initial.content_json as ProseMirrorDoc) : '',
    editorProps: {
      attributes: { class: 'journal-prose editor-surface', 'aria-label': 'Journal text' },
      // Images aren't supported: swallow dropped/pasted files instead of inserting them.
      handleDrop: (_view, event) => {
        if (event.dataTransfer?.files?.length) {
          message.info("Photos aren't supported yet")
          return true
        }
        return false
      },
      handlePaste: (_view, event) => {
        if (event.clipboardData?.files?.length) {
          message.info("Photos aren't supported yet")
          return true
        }
        return false
      },
    },
    onUpdate: ({ editor: e }) => update({ content_json: e.getJSON() as ProseMirrorDoc }),
  })

  // Offer to restore changes that never reached the server (crash, closed tab offline).
  const offeredRestore = useRef(false)
  useEffect(() => {
    if (offeredRestore.current || !editor) return
    offeredRestore.current = true
    const local = readLocalDraft(initial.id)
    if (!local || Object.keys(local.changes).length === 0) return
    modal.confirm({
      title: 'Restore unsaved changes?',
      content: `This journal has changes from ${dayjs(local.savedAt).format('D MMM, HH:mm')} that weren't saved.`,
      okText: 'Restore',
      cancelText: 'Discard',
      onOk: () => {
        const c = local.changes
        if (c.title !== undefined) setTitle(c.title)
        if (c.subtitle !== undefined) setSubtitle(c.subtitle ?? '')
        if (c.content_json) editor.commands.setContent(c.content_json)
        if (c.visibility) setVisibility(c.visibility)
        if (c.tags) setTags(c.tags)
        update(c)
      },
      onCancel: () => {
        try {
          localStorage.removeItem(`gt:draft:${initial.id}`)
        } catch {
          /* ignore */
        }
      },
    })
  }, [editor, initial.id, modal, update])

  // Ctrl/Cmd+S forces a save.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        void autosave.flush()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [autosave])

  const change = (c: Changes) => {
    setPublishErrors([])
    update(c)
  }

  const published = journal.status === 'published'

  const runAction = async (kind: 'publish' | 'unpublish') => {
    setBusy(kind)
    setPublishErrors([])
    try {
      await autosave.flush()
      const res = kind === 'publish' ? await journals.publish(journal.id) : await journals.unpublish(journal.id)
      autosave.setVersion(res.version)
      setJournal(res)
      queryClient.invalidateQueries({ queryKey: ['feed'] })
      if (kind === 'publish') {
        message.success('Published!')
        navigate(`/j/${res.slug}`)
      } else {
        message.success('Moved back to drafts')
      }
    } catch (err) {
      if (err instanceof ApiError && err.errors.length) setPublishErrors(err.errors.map((e) => e.message))
      else message.error(errorMessage(err))
    } finally {
      setBusy(null)
    }
  }

  const remove = () =>
    modal.confirm({
      title: 'Delete this journal?',
      content: "This can't be undone.",
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: async () => {
        setBusy('delete')
        try {
          await journals.remove(journal.id)
          message.success('Journal deleted')
          navigate('/me/drafts')
        } catch (err) {
          message.error(errorMessage(err))
          setBusy(null)
        }
      },
    })

  const togglePreview = async () => {
    if (!preview) await autosave.flush()
    setPreview((p) => !p)
  }

  const share = async () => {
    const url = shareLink(journal.slug, journal.visibility, journal.share_token)
    if (!(await tryNativeShare(journal.title, url))) setShareOpen(true)
  }

  const previewHtml = useMemo(() => sanitizeJournalHtml(journal.content_html), [journal.content_html])

  if (!editor) return <FullPageSpin />

  return (
    <div className="editor-page">
      <div className="editor-topbar">
        <Space>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)} aria-label="Back" />
          <Tag color={published ? 'green' : 'default'}>{published ? 'Published' : 'Draft'}</Tag>
          <SaveIndicator status={autosave.status} error={autosave.lastError} />
        </Space>
        <Space wrap>
          <Button icon={preview ? <EditOutlined /> : <EyeOutlined />} onClick={togglePreview}>
            {preview ? 'Edit' : 'Preview'}
          </Button>
          {published && (
            <Button icon={<ShareAltOutlined />} onClick={share}>
              Share
            </Button>
          )}
          {published ? (
            <Button onClick={() => runAction('unpublish')} loading={busy === 'unpublish'}>
              Unpublish
            </Button>
          ) : (
            <Button
              type="primary"
              onClick={() => runAction('publish')}
              loading={busy === 'publish'}
              disabled={autosave.status === 'conflict'}
            >
              Publish
            </Button>
          )}
        </Space>
      </div>

      {autosave.status === 'conflict' && (
        <Alert
          type="error"
          showIcon
          className="editor-alert"
          title="This journal was changed in another tab or device."
          description="Reload to get the latest version. Your recent changes are kept on this device and you'll be offered to restore them."
          action={<Button onClick={() => window.location.reload()}>Reload</Button>}
        />
      )}
      {publishErrors.length > 0 && (
        <Alert type="warning" showIcon className="editor-alert" title="Almost there" description={publishErrors.join(' ')} />
      )}

      <div className="editor-grid">
        <main className="editor-main">
          {preview ? (
            <article className="reader">
              <h1 className="reader-title">{journal.title || 'Untitled'}</h1>
              {journal.subtitle && <p className="reader-subtitle">{journal.subtitle}</p>}
              <div className="journal-prose" dangerouslySetInnerHTML={{ __html: previewHtml }} />
            </article>
          ) : (
            <>
              <Input.TextArea
                className="title-input"
                variant="borderless"
                placeholder="Title"
                autoSize
                maxLength={200}
                value={title}
                aria-label="Title"
                onChange={(e) => {
                  const v = e.target.value.replace(/\n/g, ' ')
                  setTitle(v)
                  change({ title: v })
                }}
                onPressEnter={(e) => {
                  e.preventDefault()
                  editor.commands.focus('start')
                }}
              />
              <Input.TextArea
                className="subtitle-input"
                variant="borderless"
                placeholder="Add a subtitle (optional)"
                autoSize
                maxLength={300}
                value={subtitle}
                aria-label="Subtitle"
                onChange={(e) => {
                  const v = e.target.value.replace(/\n/g, ' ')
                  setSubtitle(v)
                  change({ subtitle: v || null })
                }}
              />
              <div className="editor-sticky-toolbar">
                <Toolbar editor={editor} />
              </div>
              <BubbleMenu editor={editor} className="bubble-menu">
                <Button size="small" type={editor.isActive('bold') ? 'primary' : 'text'} onClick={() => editor.chain().focus().toggleBold().run()}>
                  <b>B</b>
                </Button>
                <Button size="small" type={editor.isActive('italic') ? 'primary' : 'text'} onClick={() => editor.chain().focus().toggleItalic().run()}>
                  <i>I</i>
                </Button>
                <Button size="small" type={editor.isActive('highlight') ? 'primary' : 'text'} onClick={() => editor.chain().focus().toggleHighlight().run()}>
                  <mark>H</mark>
                </Button>
              </BubbleMenu>
              <EditorContent editor={editor} />
              <Typography.Text type="secondary" className="word-count">
                {editor.storage.characterCount.words()} words
              </Typography.Text>
            </>
          )}
        </main>

        <aside className="editor-side" aria-label="Journal settings">
          <Form layout="vertical" requiredMark={false}>
            <Form.Item label="Who can read this?" extra={VISIBILITY_OPTIONS.find((o) => o.value === visibility)?.hint}>
              <Select
                value={visibility}
                options={VISIBILITY_OPTIONS.map(({ value, label }) => ({ value, label }))}
                onChange={(v: Visibility) => {
                  setVisibility(v)
                  change({ visibility: v })
                }}
              />
            </Form.Item>
            <Form.Item label="Location">
              <Button block icon={<EnvironmentOutlined />} onClick={() => setLocationOpen(true)} className="location-button">
                {location ? `${flag(location.country_code)} ${location.place_name}` : 'Add a place'}
              </Button>
            </Form.Item>
            <Form.Item label="Travel dates">
              <DatePicker.RangePicker
                style={{ width: '100%' }}
                value={dates}
                allowEmpty={[true, true]}
                format="D MMM YYYY"
                onChange={(v) => {
                  setDates(v)
                  change({
                    travel_start: v?.[0]?.format('YYYY-MM-DD') ?? null,
                    travel_end: v?.[1]?.format('YYYY-MM-DD') ?? null,
                  })
                }}
              />
            </Form.Item>
            <Form.Item label="Tags" extra="Up to 10, e.g. hiking, street-food">
              <Select
                mode="tags"
                value={tags}
                maxCount={10}
                tokenSeparators={[',', ' ']}
                open={false}
                suffix={null}
                placeholder="Add tags"
                onChange={(v: string[]) => {
                  const clean = [...new Set(v.map((t) => t.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')).filter(Boolean))].slice(0, 10)
                  setTags(clean)
                  change({ tags: clean })
                }}
              />
            </Form.Item>
          </Form>
          <Button danger type="text" icon={<DeleteOutlined />} onClick={remove} loading={busy === 'delete'}>
            Delete journal
          </Button>
        </aside>
      </div>

      {locationOpen && (
      <LocationModal
        open={locationOpen}
        value={location}
        onCancel={() => setLocationOpen(false)}
        onSave={(loc) => {
          setLocation(loc)
          setLocationOpen(false)
          change(loc ? { location: loc, clear_location: false } : { location: null, clear_location: true })
        }}
      />
      )}
      <ShareModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        title={journal.title}
        slug={journal.slug}
        visibility={journal.visibility}
        shareToken={journal.share_token}
        onRotateToken={async () => {
          const res = await journals.rotateShareToken(journal.id)
          autosave.setVersion(res.version)
          setJournal(res)
        }}
      />
    </div>
  )
}
