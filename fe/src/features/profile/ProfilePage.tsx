import { GlobalOutlined, SettingOutlined } from '@ant-design/icons'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Card, List, Modal, Result, Skeleton, Space, Statistic, Typography } from 'antd'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import { users } from '../../api/endpoints'
import type { Profile } from '../../api/types'
import { JournalList } from '../../components/JournalList'
import { UserAvatar } from '../../components/UserAvatar'
import { useSession } from '../../stores/session'
import { countryName, flag } from '../../utils/countries'
import { longDate } from '../../utils/format'

function FollowList({ username, kind, onClose }: { username: string; kind: 'followers' | 'following'; onClose: () => void }) {
  const q = useInfiniteQuery({
    queryKey: ['users', username, kind],
    queryFn: ({ pageParam }) => (kind === 'followers' ? users.followers : users.following)(username, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (p) => p.next_cursor,
  })
  const items = q.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <Modal open title={kind === 'followers' ? 'Followers' : 'Following'} onCancel={onClose} footer={null}>
      <List
        loading={q.isPending}
        dataSource={items}
        locale={{ emptyText: kind === 'followers' ? 'No followers yet' : 'Not following anyone yet' }}
        renderItem={(u) => (
          <List.Item>
            <Link to={`/u/${u.username}`} onClick={onClose} className="user-row">
              <UserAvatar user={u} />
              <span>
                <strong>{u.display_name}</strong> <Typography.Text type="secondary">@{u.username}</Typography.Text>
              </span>
            </Link>
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
    </Modal>
  )
}

function FollowButton({ profile }: { profile: Profile }) {
  const status = useSession((s) => s.status)
  const navigate = useNavigate()
  const location = useLocation()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const mut = useMutation({
    mutationFn: (follow: boolean) => (follow ? users.follow(profile.username) : users.unfollow(profile.username)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['profile', profile.username] })
      void queryClient.invalidateQueries({ queryKey: ['feed'] })
    },
    onError: (err) => message.error(errorMessage(err)),
  })
  if (status !== 'authed') {
    return (
      <Button type="primary" onClick={() => navigate('/login', { state: { from: location.pathname } })}>
        Follow
      </Button>
    )
  }
  // Distinct keys: swap in a fresh button when the state flips, rather than animating the
  // previous button's loading spinner out (which can linger after the request finished).
  return profile.is_following ? (
    <Button key="following" onClick={() => mut.mutate(false)} loading={mut.isPending}>
      Following
    </Button>
  ) : (
    <Button key="follow" type="primary" onClick={() => mut.mutate(true)} loading={mut.isPending}>
      Follow
    </Button>
  )
}

export default function ProfilePage() {
  const { username = '' } = useParams()
  const status = useSession((s) => s.status)
  const navigate = useNavigate()
  const [list, setList] = useState<'followers' | 'following' | null>(null)
  const q = useQuery({
    queryKey: ['profile', username, status],
    queryFn: () => users.get(username),
    enabled: status !== 'loading',
  })

  if (q.isPending) return <Skeleton active avatar className="page" />
  if (q.isError) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return <Result status={notFound ? '404' : 'error'} title={notFound ? 'Traveller not found' : errorMessage(q.error)} />
  }
  const p = q.data

  return (
    <div className="page">
      <Card className="profile-card">
        <div className="profile-head">
          <UserAvatar user={p} size={88} />
          <div className="profile-info">
            <Typography.Title level={2} style={{ margin: 0 }}>
              {p.display_name}
            </Typography.Title>
            <Typography.Text type="secondary">@{p.username}</Typography.Text>
            {p.bio && <Typography.Paragraph className="profile-bio">{p.bio}</Typography.Paragraph>}
            <Space size={16} wrap>
              {p.home_country && (
                <span>
                  {flag(p.home_country)} {countryName(p.home_country)}
                </span>
              )}
              {p.website_url && (
                <a href={p.website_url} target="_blank" rel="noopener nofollow ugc">
                  <GlobalOutlined /> {p.website_url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                </a>
              )}
              <Typography.Text type="secondary">Joined {longDate(p.created_at)}</Typography.Text>
            </Space>
          </div>
          <div className="profile-actions">
            {p.is_me ? (
              <Button icon={<SettingOutlined />} onClick={() => navigate('/settings')}>
                Edit profile
              </Button>
            ) : (
              <FollowButton profile={p} />
            )}
          </div>
        </div>
        <Space size={32} className="profile-stats">
          <Statistic title="Journals" value={p.journal_count} />
          <button type="button" className="stat-button" onClick={() => setList('followers')}>
            <Statistic title="Followers" value={p.follower_count} />
          </button>
          <button type="button" className="stat-button" onClick={() => setList('following')}>
            <Statistic title="Following" value={p.following_count} />
          </button>
        </Space>
      </Card>

      <Typography.Title level={3}>Journals</Typography.Title>
      <JournalList
        queryKey={['feed', 'profile', p.username, status]}
        fetchPage={(cursor) => users.journals(p.username, cursor)}
        empty={<Typography.Paragraph type="secondary">No published journals yet.</Typography.Paragraph>}
      />
      {list && <FollowList username={p.username} kind={list} onClose={() => setList(null)} />}
    </div>
  )
}
