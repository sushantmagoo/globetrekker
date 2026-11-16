import { Input, Segmented, Select, Space, Tag, Typography } from 'antd'
import { useSearchParams } from 'react-router'
import { feed } from '../../api/endpoints'
import { JournalList } from '../../components/JournalList'
import { COUNTRY_OPTIONS, countryName, flag } from '../../utils/countries'

export default function ExplorePage() {
  const [params, setParams] = useSearchParams()
  const sort = params.get('sort') === 'trending' ? 'trending' : 'recent'
  const tag = params.get('tag') ?? ''
  const country = params.get('country') ?? ''

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }

  return (
    <div className="page">
      <div className="page-header">
        <Typography.Title level={2}>Explore</Typography.Title>
      </div>
      <Space wrap size="middle" className="explore-filters">
        <Segmented
          value={sort}
          onChange={(v) => set('sort', v === 'recent' ? '' : String(v))}
          options={[
            { value: 'recent', label: 'Recent' },
            { value: 'trending', label: 'Trending' },
          ]}
        />
        <Select
          showSearch
          allowClear
          placeholder="Any country"
          style={{ width: 220 }}
          value={country || undefined}
          options={COUNTRY_OPTIONS}
          optionFilterProp="name"
          onChange={(v?: string) => set('country', v ?? '')}
          aria-label="Filter by country"
        />
        <Input.Search
          placeholder="Tag, e.g. hiking"
          allowClear
          defaultValue={tag}
          key={tag}
          style={{ width: 220 }}
          onSearch={(v) => set('tag', v.trim().toLowerCase().replace(/^#/, ''))}
          aria-label="Filter by tag"
        />
      </Space>
      {(tag || country) && (
        <div className="active-filters">
          {tag && (
            <Tag closable onClose={() => set('tag', '')}>
              #{tag}
            </Tag>
          )}
          {country && (
            <Tag closable onClose={() => set('country', '')}>
              {flag(country)} {countryName(country)}
            </Tag>
          )}
        </div>
      )}
      <JournalList
        queryKey={['feed', 'explore', sort, tag, country]}
        fetchPage={(cursor) => feed.explore({ sort, tag: tag || undefined, country: country || undefined }, cursor)}
      />
    </div>
  )
}
