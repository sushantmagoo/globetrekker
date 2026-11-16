import { Link } from 'react-router'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="brand" aria-label="Globetrekker home">
      <img src="/logo.png" alt="" width={32} height={32} />
      {!compact && <span className="brand-name">Globetrekker</span>}
    </Link>
  )
}
