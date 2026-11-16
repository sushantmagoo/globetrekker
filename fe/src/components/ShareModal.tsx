import {
  CopyOutlined,
  FacebookFilled,
  MailOutlined,
  ReloadOutlined,
  SendOutlined,
  WhatsAppOutlined,
  XOutlined,
} from '@ant-design/icons'
import { Alert, App, Button, Input, Modal, Space, Typography } from 'antd'
import type { Visibility } from '../api/types'
import { journalUrl } from '../utils/format'

interface Props {
  open: boolean
  onClose: () => void
  title: string
  slug: string
  visibility: Visibility
  shareToken?: string | null
  /** Owner only: rotate the unlisted link token. */
  onRotateToken?: () => Promise<void>
}

const VISIBILITY_NOTE: Partial<Record<Visibility, string>> = {
  followers: 'Only people who follow you can open this link.',
  private: 'This journal is private. Only you can open this link.',
  unlisted: 'Anyone with this link can read the journal. It is not listed anywhere else.',
}

export function shareLink(slug: string, visibility: Visibility, shareToken?: string | null): string {
  return journalUrl(slug, visibility === 'unlisted' ? shareToken : null)
}

/** Opens the native share sheet when available (mobile); returns false to fall back to the modal. */
export async function tryNativeShare(title: string, url: string): Promise<boolean> {
  const isTouch = window.matchMedia?.('(pointer: coarse)').matches
  if (!isTouch || typeof navigator.share !== 'function') return false
  try {
    await navigator.share({ title, text: title, url })
  } catch {
    /* user cancelled */
  }
  return true
}

export function ShareModal({ open, onClose, title, slug, visibility, shareToken, onRotateToken }: Props) {
  const { message, modal } = App.useApp()
  const url = shareLink(slug, visibility, shareToken)
  const text = `${title} — on Globetrekker`
  const enc = encodeURIComponent

  const targets = [
    { key: 'x', label: 'X', icon: <XOutlined />, href: `https://twitter.com/intent/tweet?url=${enc(url)}&text=${enc(text)}` },
    { key: 'fb', label: 'Facebook', icon: <FacebookFilled />, href: `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}` },
    { key: 'wa', label: 'WhatsApp', icon: <WhatsAppOutlined />, href: `https://wa.me/?text=${enc(`${text} ${url}`)}` },
    { key: 'tg', label: 'Telegram', icon: <SendOutlined />, href: `https://t.me/share/url?url=${enc(url)}&text=${enc(text)}` },
    { key: 'mail', label: 'Email', icon: <MailOutlined />, href: `mailto:?subject=${enc(text)}&body=${enc(url)}` },
  ]

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      message.success('Link copied')
    } catch {
      message.error('Could not copy. Select the link and copy it manually.')
    }
  }

  const rotate = () =>
    modal.confirm({
      title: 'Create a new link?',
      content: 'The current link will stop working for anyone you already shared it with.',
      okText: 'Create new link',
      onOk: onRotateToken,
    })

  return (
    <Modal open={open} onCancel={onClose} footer={null} title="Share journal" destroyOnHidden>
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        {VISIBILITY_NOTE[visibility] && (
          <Alert type={visibility === 'unlisted' ? 'info' : 'warning'} showIcon title={VISIBILITY_NOTE[visibility]} />
        )}
        <Space.Compact style={{ width: '100%' }}>
          <Input value={url} readOnly aria-label="Share link" onFocus={(e) => e.target.select()} />
          <Button type="primary" icon={<CopyOutlined />} onClick={copy}>
            Copy
          </Button>
        </Space.Compact>
        {visibility !== 'private' && (
          <Space wrap>
            {targets.map((t) => (
              <Button key={t.key} icon={t.icon} href={t.href} target="_blank" rel="noopener noreferrer">
                {t.label}
              </Button>
            ))}
          </Space>
        )}
        {visibility === 'unlisted' && onRotateToken && (
          <Typography.Text type="secondary">
            Shared it with the wrong people?{' '}
            <Button type="link" size="small" icon={<ReloadOutlined />} onClick={rotate} style={{ padding: 0 }}>
              Create a new link
            </Button>
          </Typography.Text>
        )}
      </Space>
    </Modal>
  )
}
