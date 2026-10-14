import { useEffect, useRef } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { toyDetailQuery } from '../api/catalog'
import { ExposureBadge } from './ExposureBadge'
import { QueryError } from './QueryError'

type Props = {
  finisherId: string
  toyId: string
  onBack: () => void
}

export function ToyDetails({ finisherId, toyId, onBack }: Props) {
  const query = useInfiniteQuery(toyDetailQuery(finisherId, toyId))
  const detail = query.data?.pages[0]
  const parts = query.data?.pages.flatMap((page) => page.parts) ?? []
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => { heading.current?.focus() }, [])

  return (
    <section aria-labelledby="toy-heading">
      <button type="button" className="back-button" onClick={onBack}>← Back to toys</button>
      <h2 id="toy-heading" ref={heading} tabIndex={-1}>
        {detail ? detail.toy_name : 'Toy details'}
      </h2>
      {query.isPending && <p role="status">Loading toy trace…</p>}
      {query.isError && !query.isFetchNextPageError && (
        <QueryError
          message="Could not load this toy’s trace. It may no longer be in this Finisher’s catalog. Try again or return to toys."
          retry={() => { void query.refetch() }}
          isFetching={query.isFetching}
        />
      )}
      {detail && (!query.isError || query.isFetchNextPageError) && (
        <>
          <p className="record-id">{detail.toy_id}</p>
          <ExposureBadge status={detail.exposure_status} />
          <dl className="listing-facts">
            <div><dt>Retail price (USD)</dt><dd>{detail.retail_price_usd}</dd></div>
            <div><dt>Units per year</dt><dd>{detail.units_per_year.toLocaleString()}</dd></div>
          </dl>
          <h3>Bill of materials & traceability</h3>
          <p>All listed sources are possible exposure paths, not proof of an actual purchase.
            An unflagged alternate source does not eliminate possible exposure.</p>
          <p className="muted">Path: Finisher → Toy → Part → Factory → Supplier. Quantities are per toy, not per source.</p>
          <p>{detail.total_parts} parts total · {parts.length} loaded</p>
          {parts.length === 0 && <p role="status">No BOM parts recorded for this toy.</p>}
          {parts.map((part) => (
            <article className="part-card" key={part.part_id} aria-labelledby={`part-${encodeURIComponent(part.part_id)}`}>
              <header className="part-header">
                <div>
                  <h4 id={`part-${encodeURIComponent(part.part_id)}`}>{part.part_name}</h4>
                  <span className="record-id">{part.part_id}</span>
                </div>
                <p className="quantity">Quantity per toy: <strong>{part.quantity}</strong></p>
              </header>
              {part.source_uncertainty && <p className="uncertainty">{part.source_uncertainty}</p>}
              {part.sources.length === 0 && <p>No listed manufacturing sources for this part.</p>}
              <ul className="source-list" aria-label={`Sources for ${part.part_name}`}>
                {part.sources.map((source) => (
                  <li
                    key={source.factory.factory_id}
                    className={`trace-path ${source.supplier.is_flagged ? 'flagged-path' : ''}`}
                  >
                    <p className="path-status">
                      {source.supplier.is_flagged
                        ? 'Flagged path — supplier flagged by this Finisher'
                        : 'Supplier not flagged by this Finisher'}
                    </p>
                    <dl className="source-facts">
                      <div>
                        <dt>Factory</dt>
                        <dd>{source.factory.factory_name} <span className="record-id">{source.factory.factory_id}</span></dd>
                        <dd className="muted">{[source.factory.address_line, source.factory.city, source.factory.country].filter(Boolean).join(', ')}</dd>
                      </div>
                      <div>
                        <dt>Supplier</dt>
                        <dd>{source.supplier.supplier_name} <span className="record-id">{source.supplier.supplier_id}</span></dd>
                        <dd className="muted">{source.supplier.hq_country}</dd>
                      </div>
                      <div><dt>Unit cost (USD)</dt><dd>{source.unit_cost_usd}</dd></div>
                    </dl>
                    <p className="path-chain">
                      {finisherId} → {toyId} → {part.part_id} → {source.factory.factory_id} → {source.supplier.supplier_id}
                    </p>
                  </li>
                ))}
              </ul>
            </article>
          ))}
          {query.isFetchNextPageError && <p role="alert">Could not load more parts. Try again.</p>}
          {query.hasNextPage && <button type="button" disabled={query.isFetching} onClick={() => { void query.fetchNextPage() }}>
            {query.isFetchingNextPage ? 'Loading more…' : 'Load more'}
          </button>}
        </>
      )}
    </section>
  )
}
