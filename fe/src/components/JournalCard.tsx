import {
  ClockCircleOutlined,
  EnvironmentOutlined,
  EyeInvisibleOutlined,
  HeartOutlined,
  LockOutlined,
  MessageOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import { Card, Space, Tag, Tooltip, Typography } from 'antd'
import { Link } from 'react-router'
import type { JournalCard as JournalCardT, Visibility } from '../api/types'
import { flag } from '../utils/countries'
import { fromNow, travelRange } from '../utils/format'
import { UserAvatar } from './UserAvatar'

const VISIBILITY_ICON: Record<Visibility, React.ReactNode> = {
  public: null,
  followers: (
    <Tooltip title="Followers only">
      <TeamOutlined />
    </Tooltip>
  ),
  unlisted: (
    <Tooltip title="Unlisted: only people with the link">
      <EyeInvisibleOutlined />
    </Tooltip>
  ),
  private: (
    <Tooltip title="Private: only you">
      <LockOutlined />
    </Tooltip>
  ),
}

export function JournalCard({ journal, draft = false }: { journal: JournalCardT; draft?: boolean }) {
  const href = draft ? `/write/${journal.id}` : `/j/${journal.slug}`
  const dates = travelRange(journal.travel_start, journal.travel_end)
  return (
    <Card className="journal-card" hoverable styles={{ body: { padding: 20 } }}>
      {!draft && (
        <Link to={`/u/${journal.author.username}`} className="journal-card-author">
          <UserAvatar user={journal.author} size={24} />
          <span>{journal.author.display_name}</span>
          <Typography.Text type="secondary">· {fromNow(journal.published_at)}</Typography.Text>
        </Link>
      )}
      <Link to={href} className="journal-card-link">
        <Typography.Title level={4} className="journal-card-title">
          {journal.title} {VISIBILITY_ICON[journal.visibility]}
        </Typography.Title>
        {journal.subtitle && (
          <Typography.Paragraph type="secondary" className="journal-card-subtitle">
            {journal.subtitle}
          </Typography.Paragraph>
        )}
        {journal.excerpt && (
          <Typography.Paragraph className="journal-card-excerpt" ellipsis={{ rows: 3 }}>
            {journal.excerpt}
          </Typography.Paragraph>
        )}
      </Link>
      <Space size={[16, 4]} wrap className="journal-card-meta">
        {journal.place_name && (
          <span>
            <EnvironmentOutlined /> {flag(journal.country_code)} {journal.place_name}
          </span>
        )}
        {dates && <span>{dates}</span>}
        {draft ? (
          <span>Edited {fromNow(journal.updated_at)}</span>
        ) : (
          <>
            {journal.reading_minutes > 0 && (
              <span>
                <ClockCircleOutlined /> {journal.reading_minutes} min
              </span>
            )}
            <span aria-label={`${journal.like_count} likes`}>
              <HeartOutlined /> {journal.like_count}
            </span>
            <span aria-label={`${journal.comment_count} comments`}>
              <MessageOutlined /> {journal.comment_count}
            </span>
          </>
        )}
      </Space>
      {journal.tags.length > 0 && (
        <div className="journal-card-tags">
          {journal.tags.map((t) => (
            <Link key={t} to={`/explore?tag=${encodeURIComponent(t)}`}>
              <Tag>#{t}</Tag>
            </Link>
          ))}
        </div>
      )}
    </Card>
  )
}
