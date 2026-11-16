import { Avatar } from 'antd'
import type { UserSummary } from '../api/types'

const PALETTE = ['#4f7a28', '#7a6a12', '#2f6f73', '#8a4b2a', '#5b4a8a', '#2e5e8c', '#8c2e55', '#3e7a57']

export function avatarColor(username: string): string {
  let h = 0
  for (const ch of username) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  const letters = parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : (parts[0] ?? '?').slice(0, 2)
  return letters.toUpperCase()
}

export function UserAvatar({ user, size = 32 }: { user: UserSummary; size?: number }) {
  return (
    <Avatar
      size={size}
      style={{ backgroundColor: avatarColor(user.username), flexShrink: 0, fontSize: size * 0.4 }}
      aria-label={user.display_name}
    >
      {initials(user.display_name)}
    </Avatar>
  )
}
