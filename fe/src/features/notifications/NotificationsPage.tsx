import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Empty, List, Typography } from 'antd'
import { useEffect } from 'react'
import { Link } from 'react-router'
import { errorMessage } from '../../api/client'
import { notifications } from '../../api/endpoints'
import type { Notification } from '../../api/types'
import { UserAvatar } from '../../components/UserAvatar'
import { fromNow } from '../../utils/format'

function describe(n: Notification) {
  const journal = n.journal_slug ? (
    <Link to={`/j/${n.journal_slug}`}>{n.journal_title || 'your journal'}</Link>
  ) : (
    'your journal'
  )
  switch (n.type) {
    case 'follow':
      return 'started following you'
    case 'like':
      return <>liked {journal}</>
    case 'comment':
      return <>commented on {journal}</>
    case 'reply':
      return <>replied to your comment on {journal}</>
  }
}

export default function NotificationsPage() {
  const queryClient = useQueryClient()
  const q = useInfiniteQuery({
    queryKey: ['notifications', 'list'],
    queryFn: ({ pageParam }) => notifications.list(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (p) => p.next_cursor,
  })

  // Opening the page marks everything as read (the list keeps showing what was unread).
  useEffect(() => {
    if (!q.isSuccess) return
    const hasUnread = q.data.pages.some((p) => p.items.some((n) => !n.read_at))
    if (hasUnread) {
      notifications
        .markRead()
        .then(() => queryClient.setQueryData(['notifications', 'unread'], { count: 0 }))
        .catch(() => undefined)
    }
  }, [q.isSuccess, q.data, queryClient])

  const items = q.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <div className="page narrow">
      <Typography.Title level={2}>Notifications</Typography.Title>
      {q.isError && <Alert type="error" title={errorMessage(q.error)} />}
      <List
        loading={q.isPending}
        dataSource={items}
        locale={{ emptyText: <Empty description="No notifications yet" /> }}
        renderItem={(n) => (
          <List.Item className={n.read_at ? 'notification' : 'notification unread'}>
            <List.Item.Meta
              avatar={
                <Link to={`/u/${n.actor.username}`}>
                  <UserAvatar user={n.actor} size={40} />
                </Link>
              }
              title={
                <span>
                  <Link to={`/u/${n.actor.username}`}>{n.actor.display_name}</Link> {describe(n)}
                </span>
              }
              description={fromNow(n.created_at)}
            />
          </List.Item>
        )}
        loadMore={
          q.hasNextPage ? (
            <div className="load-more">
              <Button onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>
                Load more
              </Button>
            </div>
          ) : null
        }
      />
    </div>
  )
}
