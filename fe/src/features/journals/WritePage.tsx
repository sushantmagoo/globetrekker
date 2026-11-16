import { Result } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { errorMessage } from '../../api/client'
import { journals } from '../../api/endpoints'
import { FullPageSpin } from '../../components/RequireAuth'

/** /write — creates an empty draft, then opens it in the editor. */
export default function WritePage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false) // StrictMode runs effects twice in dev

  useEffect(() => {
    if (started.current) return
    started.current = true
    journals
      .create()
      .then((j) => navigate(`/write/${j.id}`, { replace: true }))
      .catch((err) => setError(errorMessage(err)))
  }, [navigate])

  if (error) {
    return <Result status="error" title="Could not start a new journal" subTitle={error} extra={<Link to="/">Go home</Link>} />
  }
  return <FullPageSpin />
}
