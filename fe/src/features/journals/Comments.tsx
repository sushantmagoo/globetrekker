import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App, Button, Empty, Input, Space, Typography } from 'antd'
import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { errorMessage } from '../../api/client'
import { comments as commentsApi } from '../../api/endpoints'
import type { Comment } from '../../api/types'
import { UserAvatar } from '../../components/UserAvatar'
import { useSession } from '../../stores/session'
import { fromNow } from '../../utils/format'

interface Props {
  journalId: string
  shareToken: string | null
}

function CommentForm({
  onSubmit,
  placeholder,
  autoFocus,
  onCancel,
  initial = '',
  submitLabel = 'Post',
}: {
  onSubmit: (body: string) => Promise<unknown>
  placeholder: string
  autoFocus?: boolean
  onCancel?: () => void
  initial?: string
  submitLabel?: string
}) {
  const [body, setBody] = useState(initial)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!body.trim()) return
    setBusy(true)
    try {
      await onSubmit(body.trim())
      setBody('')
    } finally {
      setBusy(false)
    }
  }
  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Input.TextArea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={placeholder}
        autoSize={{ minRows: 2, maxRows: 8 }}
        maxLength={2000}
        autoFocus={autoFocus}
        aria-label={placeholder}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') void submit()
        }}
      />
      <Space>
        <Button type="primary" size="small" onClick={submit} loading={busy} disabled={!body.trim()}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button size="small" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </Space>
    </Space>
  )
}

function CommentItem({
  comment,
  canReply,
  onReply,
  onChanged,
}: {
  comment: Comment
  canReply: boolean
  onReply: (parentId: string, body: string) => Promise<unknown>
  onChanged: () => void
}) {
  const { message, modal } = App.useApp()
  const [replying, setReplying] = useState(false)
  const [editing, setEditing] = useState(false)

  const remove = () =>
    modal.confirm({
      title: 'Delete this comment?',
      content: comment.parent_id ? undefined : 'Replies to it will be deleted too.',
      okText: 'Delete',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await commentsApi.remove(comment.id)
          onChanged()
        } catch (err) {
          message.error(errorMessage(err))
        }
      },
    })

  return (
    <div className="comment">
      <Link to={`/u/${comment.author.username}`}>
        <UserAvatar user={comment.author} size={32} />
      </Link>
      <div className="comment-body">
        <div className="comment-head">
          <Link to={`/u/${comment.author.username}`} className="comment-author">
            {comment.author.display_name}
          </Link>
          <Typography.Text type="secondary">
            {fromNow(comment.created_at)}
            {comment.edited_at && ' · edited'}
          </Typography.Text>
        </div>
        {editing ? (
          <CommentForm
            initial={comment.body}
            placeholder="Edit your comment"
            submitLabel="Save"
            autoFocus
            onCancel={() => setEditing(false)}
            onSubmit={async (body) => {
              try {
                await commentsApi.edit(comment.id, body)
                setEditing(false)
                onChanged()
              } catch (err) {
                message.error(errorMessage(err))
              }
            }}
          />
        ) : (
          <Typography.Paragraph className="comment-text">{comment.body}</Typography.Paragraph>
        )}
        {!editing && (
          <Space size={4} className="comment-actions">
            {canReply && !comment.parent_id && (
              <Button type="link" size="small" onClick={() => setReplying((r) => !r)}>
                Reply
              </Button>
            )}
            {comment.can_edit && (
              <Button type="link" size="small" onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {comment.can_delete && (
              <Button type="link" size="small" danger onClick={remove}>
                Delete
              </Button>
            )}
          </Space>
        )}
        {replying && (
          <CommentForm
            placeholder={`Reply to ${comment.author.display_name}`}
            autoFocus
            onCancel={() => setReplying(false)}
            onSubmit={async (body) => {
              await onReply(comment.id, body)
              setReplying(false)
            }}
          />
        )}
        {comment.replies.length > 0 && (
          <div className="comment-replies">
            {comment.replies.map((r) => (
              <CommentItem key={r.id} comment={r} canReply={false} onReply={onReply} onChanged={onChanged} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function Comments({ journalId, shareToken }: Props) {
  const { message } = App.useApp()
  const user = useSession((s) => s.user)
  const location = useLocation()
  const queryClient = useQueryClient()
  const key = ['comments', journalId]
  const q = useQuery({ queryKey: key, queryFn: () => commentsApi.list(journalId, shareToken) })

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: key })
    void queryClient.invalidateQueries({ queryKey: ['journal'] })
  }

  const add = useMutation({
    mutationFn: ({ body, parentId }: { body: string; parentId?: string }) =>
      commentsApi.add(journalId, body, parentId, shareToken),
    onSuccess: refresh,
    onError: (err) => message.error(errorMessage(err)),
  })

  const canComment = Boolean(user)
  const total = (q.data ?? []).reduce((n, c) => n + 1 + c.replies.length, 0)

  return (
    <section className="comments" aria-labelledby="comments-heading">
      <Typography.Title level={4} id="comments-heading">
        Comments {total > 0 && <Typography.Text type="secondary">({total})</Typography.Text>}
      </Typography.Title>

      {canComment ? (
        <CommentForm placeholder="Share your thoughts" onSubmit={(body) => add.mutateAsync({ body })} />
      ) : (
        <Typography.Paragraph>
          <Link to="/login" state={{ from: location.pathname + location.search }}>
            Log in
          </Link>{' '}
          to join the conversation.
        </Typography.Paragraph>
      )}

      <div className="comment-list">
        {q.isError && <Alert type="error" title={errorMessage(q.error)} />}
        {q.data?.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No comments yet" />}
        {q.data?.map((c) => (
          <CommentItem
            key={c.id}
            comment={c}
            canReply={canComment}
            onReply={(parentId, body) => add.mutateAsync({ body, parentId })}
            onChanged={refresh}
          />
        ))}
      </div>
    </section>
  )
}
