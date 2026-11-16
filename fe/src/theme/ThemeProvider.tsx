import { App as AntApp, ConfigProvider, theme as antTheme } from 'antd'
import { useEffect, useState, type ReactNode } from 'react'
import { useUi } from '../stores/ui'

export const BRAND = {
  green: '#4f7a28', // primary (logo green, darkened for AA contrast)
  greenLight: '#9bc068', // logo ring
  sun: '#e8d86a', // logo sun / mountain
  ink: '#1f1f1f',
}

const FONT_UI = `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`

function useSystemDark(): boolean {
  const query = '(prefers-color-scheme: dark)'
  const [dark, setDark] = useState(() => window.matchMedia?.(query).matches ?? false)
  useEffect(() => {
    const mql = window.matchMedia?.(query)
    if (!mql) return
    const onChange = (e: MediaQueryListEvent) => setDark(e.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return dark
}

export function useIsDark(): boolean {
  const pref = useUi((s) => s.theme)
  const systemDark = useSystemDark()
  return pref === 'dark' || (pref === 'system' && systemDark)
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const dark = useIsDark()

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  }, [dark])

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: {
          colorPrimary: dark ? BRAND.greenLight : BRAND.green,
          colorLink: dark ? BRAND.greenLight : BRAND.green,
          fontFamily: FONT_UI,
          borderRadius: 8,
          colorBgLayout: dark ? '#141414' : '#f7f5ee',
        },
        components: {
          Layout: {
            headerBg: dark ? '#1b1b1b' : '#ffffff',
            bodyBg: dark ? '#141414' : '#f7f5ee',
            headerPadding: '0 16px',
          },
        },
      }}
    >
      <AntApp>{children}</AntApp>
    </ConfigProvider>
  )
}
