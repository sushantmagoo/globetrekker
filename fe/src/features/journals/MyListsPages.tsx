import { EditOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Empty, Skeleton, Typography } from 'antd'
import { Link, useNavigate } from 'react-router'
import { errorMessage } from '../../api/client'
import { me } from '../../api/endpoints'
import { JournalCard } from '../../components/JournalCard'

export function DraftsPage() {
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['me', 'drafts'], queryFn: me.drafts })
  return (
    <div className="page">
      <div className="page-header">
        <Typography.Title level={2}>Drafts</Typography.Title>
        <Button type="primary" icon={<EditOutlined />} onClick={() => navigate('/write')}>
          New journal
        </Button>
      </div>
      {q.isPending && <Skeleton active />}
      {q.isError && <Alert type="error" title={errorMessage(q.error)} />}
      {q.data?.length === 0 && <Empty description="No drafts. Start writing!" />}
      <div className="journal-list">
        {q.data?.map((j) => (
          <JournalCard key={j.id} journal={j} draft />
        ))}
      </div>
    </div>
  )
}

export function BookmarksPage() {
  const q = useQuery({ queryKey: ['me', 'bookmarks'], queryFn: me.bookmarks })
  return (
    <div className="page">
      <div className="page-header">
        <Typography.Title level={2}>Bookmarks</Typography.Title>
      </div>
      {q.isPending && <Skeleton active />}
      {q.isError && <Alert type="error" title={errorMessage(q.error)} />}
      {q.data?.length === 0 && (
        <Empty
          description={
            <>
              Nothing saved yet. <Link to="/explore">Explore journals</Link>
            </>
          }
        />
      )}
      <div className="journal-list">
        {q.data?.map((j) => (
          <JournalCard key={j.id} journal={j} />
        ))}
      </div>
    </div>
  )
}
