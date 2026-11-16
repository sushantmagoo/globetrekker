import { CompassOutlined, EditOutlined } from '@ant-design/icons'
import { Button, Empty, Space, Typography } from 'antd'
import { Link, useNavigate } from 'react-router'
import { feed } from '../../api/endpoints'
import { JournalList } from '../../components/JournalList'
import { FullPageSpin } from '../../components/RequireAuth'
import { useSession } from '../../stores/session'

export default function HomePage() {
  const status = useSession((s) => s.status)
  const user = useSession((s) => s.user)
  const navigate = useNavigate()

  if (status === 'loading') return <FullPageSpin />

  if (status === 'anon') {
    return (
      <div className="page">
        <section className="hero">
          <img src="/logo.png" alt="" width={88} height={88} />
          <h1 className="hero-title">Every trip deserves a story.</h1>
          <p className="hero-sub">
            Globetrekker is a journal for travellers. Write about the places you go, keep them private or share
            them with the world, and follow other people on their journeys.
          </p>
          <Space>
            <Button type="primary" size="large" onClick={() => navigate('/signup')}>
              Start your journal
            </Button>
            <Button size="large" icon={<CompassOutlined />} onClick={() => navigate('/explore')}>
              Explore
            </Button>
          </Space>
        </section>
        <Typography.Title level={3}>Fresh from the road</Typography.Title>
        <JournalList queryKey={['feed', 'explore', 'recent', '', '']} fetchPage={(c) => feed.explore({ sort: 'recent' }, c)} />
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <Typography.Title level={2}>Welcome back, {user?.display_name.split(' ')[0]}</Typography.Title>
        <Button type="primary" icon={<EditOutlined />} onClick={() => navigate('/write')}>
          Write a journal
        </Button>
      </div>
      <JournalList
        queryKey={['feed', 'home']}
        fetchPage={feed.home}
        empty={
          <Empty
            description={
              <>
                Your feed is empty. Journals from people you follow show up here.
                <br />
                <Link to="/explore">Find travellers to follow</Link>
              </>
            }
          />
        }
      />
    </div>
  )
}
