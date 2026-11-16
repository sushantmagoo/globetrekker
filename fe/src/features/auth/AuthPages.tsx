import { Alert, App, Button, Card, Form, Input, Typography } from 'antd'
import { useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { errorMessage } from '../../api/client'
import { auth } from '../../api/endpoints'
import { applyFieldErrors, PASSWORD_RULES } from './forms'

function AuthCard({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="auth-page">
      <Card className="auth-card">
        <div className="auth-logo">
          <img src="/logo.png" alt="" width={56} height={56} />
        </div>
        <Typography.Title level={3} className="auth-title">
          {title}
        </Typography.Title>
        {children}
      </Card>
      {footer && <div className="auth-footer">{footer}</div>}
    </div>
  )
}

export function LoginPage() {
  const [form] = Form.useForm<{ email: string; password: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const from = (location.state as { from?: string } | null)?.from ?? '/'

  const submit = async (v: { email: string; password: string }) => {
    setBusy(true)
    setError(null)
    try {
      await auth.login(v)
      navigate(from, { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="Welcome back"
      footer={
        <>
          New to Globetrekker? <Link to="/signup">Create an account</Link>
        </>
      }
    >
      {error && <Alert type="error" showIcon title={error} className="auth-alert" />}
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: 'Enter your email' }]}>
          <Input autoComplete="email" autoFocus />
        </Form.Item>
        <Form.Item name="password" label="Password" rules={[{ required: true, message: 'Enter your password' }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={busy}>
          Log in
        </Button>
      </Form>
    </AuthCard>
  )
}

interface SignupValues {
  display_name: string
  username: string
  email: string
  password: string
}

export function SignupPage() {
  const [form] = Form.useForm<SignupValues>()
  const navigate = useNavigate()
  const { message } = App.useApp()
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const usernameTouched = useRef(false)

  const submit = async (v: SignupValues) => {
    setBusy(true)
    setError(null)
    try {
      await auth.signup(v)
      message.success('Welcome to Globetrekker!')
      navigate('/write', { replace: true })
    } catch (err) {
      if (!applyFieldErrors(form, err)) setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthCard
      title="Start your travel journal"
      footer={
        <>
          Already have an account? <Link to="/login">Log in</Link>
        </>
      }
    >
      {error && <Alert type="error" showIcon title={error} className="auth-alert" />}
      <Form
        form={form}
        layout="vertical"
        onFinish={submit}
        requiredMark={false}
        onValuesChange={(changed: Partial<SignupValues>) => {
          if ('username' in changed) usernameTouched.current = true
          if ('display_name' in changed && !usernameTouched.current) {
            const suggestion = (changed.display_name ?? '')
              .toLowerCase()
              .normalize('NFKD')
              .replace(/[^a-z0-9]+/g, '_')
              .replace(/^_+|_+$/g, '')
              .slice(0, 30)
            form.setFieldValue('username', suggestion)
          }
        }}
      >
        <Form.Item name="display_name" label="Your name" rules={[{ required: true, whitespace: true, message: 'Enter your name' }]}>
          <Input autoComplete="name" maxLength={80} autoFocus />
        </Form.Item>
        <Form.Item
          name="username"
          label="Username"
          extra="Your profile will be at globetrekker.me/u/username"
          normalize={(v: string) => v.toLowerCase()}
          rules={[
            { required: true, message: 'Choose a username' },
            { pattern: /^[a-z0-9_]{3,30}$/, message: '3–30 lowercase letters, numbers or underscores' },
          ]}
        >
          <Input prefix="@" autoComplete="username" maxLength={30} />
        </Form.Item>
        <Form.Item name="email" label="Email" rules={[{ required: true, type: 'email', message: 'Enter a valid email' }]}>
          <Input autoComplete="email" />
        </Form.Item>
        <Form.Item name="password" label="Password" rules={PASSWORD_RULES} extra="At least 10 characters">
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Button type="primary" htmlType="submit" block loading={busy}>
          Create account
        </Button>
      </Form>
    </AuthCard>
  )
}
