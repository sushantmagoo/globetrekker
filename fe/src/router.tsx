import { Button, Result } from 'antd'
import { lazy, Suspense, type ReactNode } from 'react'
import { createBrowserRouter, Link, useRouteError } from 'react-router'
import { AppLayout } from './components/AppLayout'
import { FullPageSpin, GuestOnly, RequireAuth } from './components/RequireAuth'
import { LoginPage, SignupPage } from './features/auth/AuthPages'
import HomePage from './features/feed/HomePage'

// Code-split heavier pages; the editor bundle (TipTap) is only loaded by writers.
const ExplorePage = lazy(() => import('./features/feed/ExplorePage'))
const JournalPage = lazy(() => import('./features/journals/JournalPage'))
const WritePage = lazy(() => import('./features/journals/WritePage'))
const EditorPage = lazy(() => import('./features/editor/EditorPage'))
const ProfilePage = lazy(() => import('./features/profile/ProfilePage'))
const NotificationsPage = lazy(() => import('./features/notifications/NotificationsPage'))
const SettingsPage = lazy(() => import('./features/settings/SettingsPage'))
const DraftsPage = lazy(() => import('./features/journals/MyListsPages').then((m) => ({ default: m.DraftsPage })))
const BookmarksPage = lazy(() =>
  import('./features/journals/MyListsPages').then((m) => ({ default: m.BookmarksPage })),
)

const page = (node: ReactNode) => <Suspense fallback={<FullPageSpin />}>{node}</Suspense>
const member = (node: ReactNode) => <RequireAuth>{page(node)}</RequireAuth>
const guest = (node: ReactNode) => <GuestOnly>{node}</GuestOnly>

function NotFound() {
  return <Result status="404" title="Page not found" extra={<Link to="/">Go home</Link>} />
}

function RouteError() {
  const error = useRouteError()
  console.error(error)
  return (
    <Result
      status="error"
      title="Something went wrong"
      subTitle="Try reloading the page."
      extra={<Button onClick={() => window.location.reload()}>Reload</Button>}
    />
  )
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'explore', element: page(<ExplorePage />) },
      { path: 'login', element: guest(<LoginPage />) },
      { path: 'signup', element: guest(<SignupPage />) },
      { path: 'write', element: member(<WritePage />) },
      { path: 'write/:id', element: member(<EditorPage />) },
      { path: 'j/:slug', element: page(<JournalPage />) },
      { path: 'u/:username', element: page(<ProfilePage />) },
      { path: 'me/drafts', element: member(<DraftsPage />) },
      { path: 'me/bookmarks', element: member(<BookmarksPage />) },
      { path: 'notifications', element: member(<NotificationsPage />) },
      { path: 'settings', element: member(<SettingsPage />) },
      { path: '*', element: <NotFound /> },
    ],
  },
])
