import { useInfiniteQuery, type QueryKey } from '@tanstack/react-query'
import { Alert, Button, Empty, Skeleton } from 'antd'
import type { ReactNode } from 'react'
import { errorMessage } from '../api/client'
import type { JournalCard as JournalCardT, Page } from '../api/types'
import { JournalCard } from './JournalCard'

interface Props {
  queryKey: QueryKey
  fetchPage: (cursor: string | null) => Promise<Page<JournalCardT>>
  empty?: ReactNode
}

export function JournalList({ queryKey, fetchPage, empty }: Props) {
  const q = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })

  if (q.isPending) {
    return (
      <div className="journal-list">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} active paragraph={{ rows: 3 }} className="journal-card-skeleton" />
        ))}
      </div>
    )
  }
  if (q.isError) return <Alert type="error" showIcon title={errorMessage(q.error)} />

  const items = q.data.pages.flatMap((p) => p.items)
  if (items.length === 0) return <>{empty ?? <Empty description="Nothing here yet" />}</>

  return (
    <div className="journal-list">
      {items.map((j) => (
        <JournalCard key={j.id} journal={j} />
      ))}
      {q.hasNextPage && (
        <div className="load-more">
          <Button onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}
    </div>
  )
}
