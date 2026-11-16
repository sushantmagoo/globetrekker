import {
  BellOutlined,
  BookOutlined,
  CompassOutlined,
  DesktopOutlined,
  EditOutlined,
  FileTextOutlined,
  HomeOutlined,
  LogoutOutlined,
  MoonOutlined,
  SettingOutlined,
  SunOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Badge, Button, Dropdown, Grid, Layout, Space, type MenuProps } from 'antd'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { auth, notifications } from '../api/endpoints'
import { useSession } from '../stores/session'
import { useUi, type ThemePref } from '../stores/ui'
import { Brand } from './Brand'
import { UserAvatar } from './UserAvatar'

const { Header, Content, Footer } = Layout

function useUnreadCount(enabled: boolean): number {
  const { data } = useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: notifications.unreadCount,
    enabled,
    refetchInterval: 60_000,
  })
  return data?.count ?? 0
}

export function AppLayout() {
  const user = useSession((s) => s.user)
  const status = useSession((s) => s.status)
  const { theme, setTheme } = useUi()
  const navigate = useNavigate()
  const location = useLocation()
  const screens = Grid.useBreakpoint()
  const mobile = !screens.md
  const unread = useUnreadCount(status === 'authed')

  const themeItems: { key: ThemePref; label: string; icon: React.ReactNode }[] = [
    { key: 'system', label: 'System theme', icon: <DesktopOutlined /> },
    { key: 'light', label: 'Light theme', icon: <SunOutlined /> },
    { key: 'dark', label: 'Dark theme', icon: <MoonOutlined /> },
  ]

  const menu: MenuProps['items'] = user
    ? [
        {
          key: 'profile',
          icon: <UserOutlined />,
          label: <Link to={`/u/${user.username}`}>Your profile</Link>,
        },
        { key: 'drafts', icon: <FileTextOutlined />, label: <Link to="/me/drafts">Drafts</Link> },
        { key: 'bookmarks', icon: <BookOutlined />, label: <Link to="/me/bookmarks">Bookmarks</Link> },
        { key: 'settings', icon: <SettingOutlined />, label: <Link to="/settings">Settings</Link> },
        { type: 'divider' },
        {
          key: 'theme',
          label: 'Theme',
          icon: theme === 'dark' ? <MoonOutlined /> : theme === 'light' ? <SunOutlined /> : <DesktopOutlined />,
          children: themeItems.map((t) => ({
            key: `theme-${t.key}`,
            icon: t.icon,
            label: t.label,
            onClick: () => setTheme(t.key),
          })),
        },
        { type: 'divider' },
        {
          key: 'logout',
          icon: <LogoutOutlined />,
          label: 'Log out',
          onClick: async () => {
            await auth.logout()
            navigate('/')
          },
        },
      ]
    : []

  const navClass = ({ isActive }: { isActive: boolean }) => (isActive ? 'nav-link active' : 'nav-link')

  return (
    <Layout className="app-layout">
      <Header className="app-header">
        <div className="app-header-inner">
          <Space size={24} align="center">
            <Brand compact={mobile} />
            {!mobile && (
              <nav className="main-nav" aria-label="Main">
                <NavLink to="/" end className={navClass}>
                  Home
                </NavLink>
                <NavLink to="/explore" className={navClass}>
                  Explore
                </NavLink>
              </nav>
            )}
          </Space>
          <Space size={mobile ? 8 : 16} align="center">
            {status === 'authed' && user ? (
              <>
                {!mobile && (
                  <Button type="primary" icon={<EditOutlined />} onClick={() => navigate('/write')}>
                    Write
                  </Button>
                )}
                {!mobile && (
                  <Link to="/notifications" aria-label={`Notifications, ${unread} unread`}>
                    <Badge count={unread} size="small">
                      <BellOutlined style={{ fontSize: 20 }} />
                    </Badge>
                  </Link>
                )}
                <Dropdown menu={{ items: menu }} trigger={['click']} placement="bottomRight">
                  <button type="button" className="avatar-button" aria-label="Account menu">
                    <UserAvatar user={user} />
                  </button>
                </Dropdown>
              </>
            ) : status === 'anon' ? (
              <>
                <Button type="text" onClick={() => navigate('/login', { state: { from: location.pathname } })}>
                  Log in
                </Button>
                <Button type="primary" onClick={() => navigate('/signup')}>
                  Sign up
                </Button>
              </>
            ) : null}
          </Space>
        </div>
      </Header>
      <Content className="app-content">
        <Outlet />
      </Content>
      {!mobile && (
        <Footer className="app-footer">
          Globetrekker · Travel journals from around the world
        </Footer>
      )}
      {mobile && status === 'authed' && user && (
        <nav className="bottom-tabs" aria-label="Main">
          <NavLink to="/" end className={navClass} aria-label="Home">
            <HomeOutlined />
          </NavLink>
          <NavLink to="/explore" className={navClass} aria-label="Explore">
            <CompassOutlined />
          </NavLink>
          <NavLink to="/write" className={navClass} aria-label="Write">
            <EditOutlined />
          </NavLink>
          <NavLink to="/notifications" className={navClass} aria-label="Notifications">
            <Badge count={unread} size="small" offset={[4, 0]}>
              <BellOutlined />
            </Badge>
          </NavLink>
          <NavLink to={`/u/${user.username}`} className={navClass} aria-label="Profile">
            <UserOutlined />
          </NavLink>
        </nav>
      )}
    </Layout>
  )
}
