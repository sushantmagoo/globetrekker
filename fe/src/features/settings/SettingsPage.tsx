import { App, Button, Card, Form, Input, Radio, Select, Space, Tabs, Typography } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { errorMessage } from '../../api/client'
import { me } from '../../api/endpoints'
import type { Visibility } from '../../api/types'
import { useSession } from '../../stores/session'
import { useUi, type ThemePref } from '../../stores/ui'
import { COUNTRY_OPTIONS } from '../../utils/countries'
import { VISIBILITY_OPTIONS } from '../../utils/visibility'
import { applyFieldErrors, PASSWORD_RULES } from '../auth/forms'

interface ProfileValues {
  display_name: string
  bio?: string
  home_country?: string
  website_url?: string
  default_visibility: Visibility
}

function ProfileTab() {
  const user = useSession((s) => s.user)!
  const setUser = useSession((s) => s.setUser)
  const { message } = App.useApp()
  const [form] = Form.useForm<ProfileValues>()
  const [busy, setBusy] = useState(false)

  const submit = async (v: ProfileValues) => {
    setBusy(true)
    try {
      const updated = await me.update({
        display_name: v.display_name,
        bio: v.bio ?? '',
        home_country: v.home_country ?? null,
        website_url: v.website_url?.trim() || null,
        default_visibility: v.default_visibility,
      })
      setUser(updated)
      message.success('Profile saved')
    } catch (err) {
      if (!applyFieldErrors(form, err)) message.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Form
      form={form}
      layout="vertical"
      requiredMark={false}
      onFinish={submit}
      initialValues={{
        display_name: user.display_name,
        bio: user.bio ?? '',
        home_country: user.home_country ?? undefined,
        website_url: user.website_url ?? '',
        default_visibility: user.default_visibility,
      }}
    >
      <Form.Item name="display_name" label="Name" rules={[{ required: true, whitespace: true }]}>
        <Input maxLength={80} />
      </Form.Item>
      <Form.Item name="bio" label="Bio">
        <Input.TextArea maxLength={500} showCount autoSize={{ minRows: 3, maxRows: 6 }} />
      </Form.Item>
      <Form.Item name="home_country" label="Home country">
        <Select showSearch allowClear options={COUNTRY_OPTIONS} optionFilterProp="name" placeholder="Select a country" />
      </Form.Item>
      <Form.Item name="website_url" label="Website" rules={[{ type: 'url', message: 'Enter a full URL, e.g. https://example.com' }]}>
        <Input placeholder="https://" />
      </Form.Item>
      <Form.Item name="default_visibility" label="Default visibility for new journals">
        <Select options={VISIBILITY_OPTIONS.map(({ value, label, hint }) => ({ value, label: `${label} — ${hint}` }))} />
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={busy}>
        Save profile
      </Button>
    </Form>
  )
}

function AccountTab() {
  const user = useSession((s) => s.user)!
  const clear = useSession((s) => s.clear)
  const { message, modal } = App.useApp()
  const navigate = useNavigate()
  const [form] = Form.useForm<{ current_password: string; new_password: string }>()
  const [busy, setBusy] = useState(false)

  const changePassword = async (v: { current_password: string; new_password: string }) => {
    setBusy(true)
    try {
      await me.changePassword(v.current_password, v.new_password)
      form.resetFields()
      message.success('Password changed')
    } catch (err) {
      if (!applyFieldErrors(form, err)) message.error(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const deleteAccount = () => {
    let typed = ''
    modal.confirm({
      title: 'Delete your account?',
      content: (
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph>
            Your profile and journals disappear immediately and are permanently deleted after 30 days. Type{' '}
            <strong>{user.username}</strong> to confirm.
          </Typography.Paragraph>
          <Input onChange={(e) => (typed = e.target.value)} aria-label="Type your username to confirm" />
        </Space>
      ),
      okText: 'Delete account',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (typed.trim().toLowerCase() !== user.username) {
          message.error('Username does not match')
          throw new Error('mismatch')
        }
        await me.remove()
        clear()
        navigate('/')
      },
    })
  }

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Card title="Email" size="small">
        {user.email}
      </Card>
      <Card title="Change password" size="small">
        <Form form={form} layout="vertical" requiredMark={false} onFinish={changePassword}>
          <Form.Item name="current_password" label="Current password" rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Form.Item name="new_password" label="New password" rules={PASSWORD_RULES}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button htmlType="submit" loading={busy}>
            Change password
          </Button>
        </Form>
      </Card>
      <Card title="Danger zone" size="small">
        <Button danger onClick={deleteAccount}>
          Delete account
        </Button>
      </Card>
    </Space>
  )
}

function AppearanceTab() {
  const { theme, setTheme } = useUi()
  return (
    <Radio.Group
      value={theme}
      onChange={(e) => setTheme(e.target.value as ThemePref)}
      options={[
        { value: 'system', label: 'Match system' },
        { value: 'light', label: 'Light' },
        { value: 'dark', label: 'Dark' },
      ]}
      optionType="button"
    />
  )
}

export default function SettingsPage() {
  return (
    <div className="page narrow">
      <Typography.Title level={2}>Settings</Typography.Title>
      <Tabs
        items={[
          { key: 'profile', label: 'Profile', children: <ProfileTab /> },
          { key: 'account', label: 'Account', children: <AccountTab /> },
          { key: 'appearance', label: 'Appearance', children: <AppearanceTab /> },
        ]}
      />
    </div>
  )
}
