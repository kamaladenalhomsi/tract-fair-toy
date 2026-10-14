import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { setSupplierFlag, supplierDetailQuery } from '../api/suppliers'
import { ExposureBadge } from './ExposureBadge'
import { QueryError } from './QueryError'

type Props = {
  finisherId: string
  supplierId: string
  onBack: () => void
}

export function SupplierDetails({ finisherId, supplierId, onBack }: Props) {
  const query = useQuery(supplierDetailQuery(finisherId, supplierId))
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: (isFlagged: boolean) => setSupplierFlag(finisherId, supplierId, isFlagged),
    onSuccess: async (result) => {
      const scope = { queryKey: ['finishers', result.finisher_id] }
      await client.cancelQueries(scope)
      await client.invalidateQueries(scope)
    },
  })
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => { heading.current?.focus() }, [])

  return (
    <section aria-labelledby="supplier-heading">
      <button type="button" className="back-button" onClick={onBack}>← Back to suppliers</button>
      <h2 id="supplier-heading" ref={heading} tabIndex={-1}>
        {query.isSuccess ? query.data.supplier.supplier_name : 'Supplier details'}
      </h2>
      {mutation.isPending && <p role="status">Saving supplier flag and refreshing this Finisher’s data…</p>}
      {mutation.isSuccess && (
        <p role="status" className="mutation-success">
          Supplier {mutation.data.is_flagged ? 'flagged' : 'unflagged'} successfully for Finisher {finisherId}.
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="error-state">
          Could not {mutation.variables ? 'flag' : 'unflag'} this supplier. {mutation.error.message}. Try the action again.
        </p>
      )}
      {query.isPending && <p role="status">Loading supplier connections…</p>}
      {query.isError && (
        <QueryError
          message="Could not load this supplier’s current connections and flag status. Try again or return to suppliers."
          retry={() => { void query.refetch() }}
          isFetching={query.isFetching}
        />
      )}
      {query.isSuccess && (
        <>
          <p className="record-id">{query.data.supplier.supplier_id} · {query.data.supplier.hq_country}</p>
          <div className="supplier-actions">
            <span className={`exposure-badge ${query.data.supplier.is_flagged ? 'affected' : 'unflagged'}`}>
              {query.data.supplier.is_flagged ? 'Flagged by this Finisher' : 'Not flagged by this Finisher'}
            </span>
            <button
              type="button"
              disabled={mutation.isPending || query.isFetching}
              onClick={() => mutation.mutate(!query.data.supplier.is_flagged)}
            >{query.data.supplier.is_flagged ? 'Unflag' : 'Flag'}</button>
          </div>
          <p>Flags record a child-labor concern for {query.data.finisher.finisher_name} only.
            Not flagged does not mean verified safe.</p>
          <h3>Connected toys</h3>
          <p className="catalog-summary">
            <strong>{query.data.connected_toys_count}</strong> distinct connected toys — each toy counted once.
            These are connections, not newly affected toys; some toys may already be potentially affected by other flagged suppliers.
          </p>
          <p>All listed sources are possible exposure paths, not proof of an actual purchase.
            Only paths to this supplier are shown. A toy remains potentially affected while any flagged supplier path remains.</p>
          <p className="muted">Path: Finisher → Toy → Part → Factory → Supplier. Quantities are per toy, not per source.</p>
          {query.data.toys.length === 0 && <p role="status">No connected toys for this supplier in this Finisher’s catalog.</p>}
          {query.data.toys.map((toy) => (
            <article className="connected-toy" key={toy.toy_id} aria-labelledby={`connected-toy-${encodeURIComponent(toy.toy_id)}`}>
              <h4 id={`connected-toy-${encodeURIComponent(toy.toy_id)}`}>{toy.toy_name}</h4>
              <p className="record-id">{toy.toy_id}</p>
              <ExposureBadge status={toy.exposure_status} />
              {toy.parts.map((part) => (
                <div className="part-card" key={part.part_id}>
                  <header className="part-header">
                    <div>
                      <h5>{part.part_name}</h5>
                      <span className="record-id">{part.part_id}</span>
                    </div>
                    <p className="quantity">Quantity per toy: <strong>{part.quantity}</strong></p>
                  </header>
                  {part.source_uncertainty && <p className="uncertainty">{part.source_uncertainty}</p>}
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
                          </div>
                          <div><dt>Unit cost (USD)</dt><dd>{source.unit_cost_usd}</dd></div>
                        </dl>
                        <p className="path-chain">
                          {finisherId} → {toy.toy_id} → {part.part_id} → {source.factory.factory_id} → {source.supplier.supplier_id}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </article>
          ))}
        </>
      )}
    </section>
  )
}
