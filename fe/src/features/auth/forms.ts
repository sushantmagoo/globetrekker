import type { FormInstance } from 'antd'
import { ApiError } from '../../api/client'

/** Map RFC 9457 field errors onto antd form fields; returns true if any were applied. */
export function applyFieldErrors(form: FormInstance, err: unknown): boolean {
  if (!(err instanceof ApiError) || err.errors.length === 0) return false
  const known = new Set(Object.keys(form.getFieldsValue()))
  const fields = err.errors
    .filter((e) => known.has(e.field))
    .map((e) => ({ name: e.field, errors: [e.message] }))
  form.setFields(fields)
  return fields.length > 0
}

export const PASSWORD_RULES = [
  { required: true, message: 'Choose a password' },
  { min: 10, message: 'At least 10 characters' },
  { max: 128, message: 'At most 128 characters' },
]
