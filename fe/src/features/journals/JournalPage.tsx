import {
  BookFilled,
  BookOutlined,
  CalendarOutlined,
  ClockCircleOutlined,
  EditOutlined,
  EnvironmentOutlined,
  HeartFilled,
  HeartOutlined,
  ShareAltOutlined,
} from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Result, Space, Tag, Tooltip, Typography } from 'antd'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router'
import { ApiError, errorMessage } from '../../api/client'
import { journals } from '../../api/endpoints'
import type { JournalDetail } from '../../api/types'
import { FullPageSpin } from '../../components/RequireAuth'
import { ShareModal, shareLink, tryNativeShare } from '../../components/ShareModal'
import { UserAvatar } from '../../components/UserAvatar'
import { useSession } from '../../stores/session'
import { countryName, flag } from '../../utils/countries'
import { longDate, travelRange } from '../../utils/format'
import { sanitizeJournalHtml } from '../../utils/sanitize'
import { Comments } from './Comments'

const PlaceMap = lazy(() => import('../../components/PlaceMap').then((m) => ({ default: m.PlaceMap })))

export default function JournalPage() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const t = params.get('t')
  const status = useSession((s) => s.status)
  const q = useQuery({
    queryKey: ['journal', slug, t, status],
    queryFn: () => journals.read(slug, t),
    enabled: status !== 'loading',
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  })

  if (q.isPending) return <FullPageSpin />
  if (q.isError) {
    const notFound = q.error instanceof ApiError && q.error.status === 404
    return (
      <Result
        status={notFound ? '404' : 'error'}
        title={notFound ? 'Journal not found' : 'Something went wrong'}
        subTitle={
          notFound
            ? "It may be private, only for the author's followers, or it no longer exists."
            : errorMessage(q.error)
        }
        extra={<Link to="/explore">Explore journals</Link>}
      />
    )
  }
  return <JournalView journal={q.data} shareToken={t} />
}

function JournalView({ journal, shareToken }: { journal: JournalDetail; shareToken: string | null }) {
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const status = useSession((s) => s.status)
  const [shareOpen, setShareOpen] = useState(false)
  const [liked, setLiked] = useState(journal.liked_by_me)
  const [likes, setLikes] = useState(journal.like_count)
  const [bookmarked, setBookmarked] = useState(journal.bookmarked_by_me)
  const html = useMemo(() => sanitizeJournalHtml(journal.content_html), [journal.content_html])
  const published = journal.status === 'published'

  useEffect(() => {
    document.title = `${journal.title} · Globetrekker`
    return () => {
      document.title = 'Globetrekker'
    }
  }, [journal.title])

  const requireLogin = () => {
    navigate('/login', { state: { from: location.pathname + location.search } })
  }

  const likeMut = useMutation({
    mutationFn: (next: boolean) => (next ? journals.like(journal.id, shareToken) : journals.unlike(journal.id)),
    onMutate: (next) => {
      setLiked(next)
      setLikes((n) => n + (next ? 1 : -1))
    },
    onError: (err, next) => {
      setLiked(!next)
      setLikes((n) => n + (next ? -1 : 1))
      message.error(errorMessage(err))
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['feed'] }),
  })

  const bookmarkMut = useMutation({
    mutationFn: (next: boolean) =>
      next ? journals.bookmark(journal.id, shareToken) : journals.unbookmark(journal.id),
    onMutate: (next) => setBookmarked(next),
    onError: (err, next) => {
      setBookmarked(!next)
      message.error(errorMessage(err))
    },
    onSuccess: (_d, next) => message.success(next ? 'Saved to bookmarks' : 'Removed from bookmarks'),
  })

  const share = async () => {
    const url = shareLink(journal.slug, journal.visibility, journal.share_token ?? shareToken)
    if (!(await tryNativeShare(journal.title, url))) setShareOpen(true)
  }

  const dates = travelRange(journal.travel_start, journal.travel_end)
  const point = journal.lat != null && journal.lng != null ? { lat: journal.lat, lng: journal.lng } : null

  return (
    <article className="reader">
      {!published && (
        <Tag color="orange" className="reader-status">
          Draft (only you can see this)
        </Tag>
      )}
      <h1 className="reader-title">{journal.title}</h1>
      {journal.subtitle && <p className="reader-subtitle">{journal.subtitle}</p>}

      <div className="reader-byline">
        <Link to={`/u/${journal.author.username}`} className="reader-author">
          <UserAvatar user={journal.author} size={40} />
          <span>
            <strong>{journal.author.display_name}</strong>
            <Typography.Text type="secondary" className="reader-date">
              {journal.published_at ? longDate(journal.published_at) : 'Not published'}
              {journal.reading_minutes > 0 && (
                <>
                  {' · '}
                  <ClockCircleOutlined /> {journal.reading_minutes} min read
                </>
              )}
            </Typography.Text>
          </span>
        </Link>
        {journal.is_owner && (
          <Button icon={<EditOutlined />} onClick={() => navigate(`/write/${journal.id}`)}>
            Edit
          </Button>
        )}
      </div>

      {(journal.place_name || dates) && (
        <Space size={[20, 4]} wrap className="reader-trip">
          {journal.place_name && (
            <span>
              <EnvironmentOutlined /> {flag(journal.country_code)} {journal.place_name}
              {journal.country_code && countryName(journal.country_code) !== journal.place_name && (
                <Typography.Text type="secondary">, {countryName(journal.country_code)}</Typography.Text>
              )}
            </span>
          )}
          {dates && (
            <span>
              <CalendarOutlined /> {dates}
            </span>
          )}
        </Space>
      )}

      <div className="journal-prose reader-body" dangerouslySetInnerHTML={{ __html: html }} />

      {point && (
        <Suspense fallback={null}>
          <div className="reader-map">
            <PlaceMap point={point} height={240} zoom={6} />
          </div>
        </Suspense>
      )}

      {journal.tags.length > 0 && (
        <div className="reader-tags">
          {journal.tags.map((tag) => (
            <Link key={tag} to={`/explore?tag=${encodeURIComponent(tag)}`}>
              <Tag>#{tag}</Tag>
            </Link>
          ))}
        </div>
      )}

      {published && (
        <div className="reader-actions">
          <Tooltip title={liked ? 'Unlike' : 'Like'}>
            <Button
              shape="round"
              icon={liked ? <HeartFilled style={{ color: '#d4380d' }} /> : <HeartOutlined />}
              onClick={() => (status === 'authed' ? likeMut.mutate(!liked) : requireLogin())}
              aria-pressed={liked}
            >
              {likes}
            </Button>
          </Tooltip>
          <Tooltip title={bookmarked ? 'Remove bookmark' : 'Bookmark'}>
            <Button
              shape="circle"
              icon={bookmarked ? <BookFilled /> : <BookOutlined />}
              onClick={() => (status === 'authed' ? bookmarkMut.mutate(!bookmarked) : requireLogin())}
              aria-label={bookmarked ? 'Remove bookmark' : 'Bookmark'}
              aria-pressed={bookmarked}
            />
          </Tooltip>
          <Button shape="round" icon={<ShareAltOutlined />} onClick={share}>
            Share
          </Button>
        </div>
      )}

      {published && <Comments journalId={journal.id} shareToken={shareToken} />}

      <ShareModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        title={journal.title}
        slug={journal.slug}
        visibility={journal.visibility}
        shareToken={journal.share_token ?? shareToken}
        onRotateToken={
          journal.is_owner
            ? async () => {
                await journals.rotateShareToken(journal.id)
                await queryClient.invalidateQueries({ queryKey: ['journal', journal.slug] })
                setShareOpen(false)
              }
            : undefined
        }
      />
    </article>
  )
}
