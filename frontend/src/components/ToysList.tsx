import { useState } from 'react'
import { Pagination } from './Pagination'
import { useQuery } from '@tanstack/react-query'
import { toysQuery } from '../api/catalog'
import { QueryError } from './QueryError'
import { ExposureBadge } from './ExposureBadge'

type Props = {
  finisherId: string
  onSelect: (toyId: string) => void
}

export function ToysList({ finisherId, onSelect }: Props) {
  const [page, setPage] = useState(1)
  const query = useQuery(toysQuery(finisherId, page))

  return (
    <section aria-labelledby="toys-heading">
      <h2 id="toys-heading">Toy catalog</h2>
      {query.isPending && <p role="status">Loading toys…</p>}
      {query.isError && (
        <QueryError
          message="Could not load this Finisher’s toys. Try again or switch Finisher."
          retry={() => { void query.refetch() }}
          isFetching={query.isFetching}
        />
      )}
      {query.isSuccess && (
        <>
          <p className="catalog-summary">
            <strong>{query.data.total_toys}</strong> toys ·{' '}
            <strong>{query.data.potentially_affected_toys}</strong> potentially affected toys
            <span className="muted"> — each toy counted once, regardless of flagged path count.</span>
          </p>
          {query.data.toys.length === 0 ? (
            <p role="status">No toys in this Finisher’s catalog. Choose another Finisher to explore.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <caption className="sr-only">Toys in the selected Finisher’s catalog</caption>
                <thead>
                  <tr>
                    <th scope="col">Toy</th>
                    <th scope="col">Exposure status</th>
                    <th scope="col">Retail price (USD)</th>
                    <th scope="col">Units per year</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.toys.map((toy) => (
                    <tr key={toy.toy_id}>
                      <th scope="row">
                        <button className="text-button" onClick={() => onSelect(toy.toy_id)}>
                          {toy.toy_name}{' '}
                          <span className="record-id">{toy.toy_id}</span>
                        </button>
                      </th>
                      <td><ExposureBadge status={toy.exposure_status} /></td>
                      <td>{toy.retail_price_usd}</td>
                      <td>{toy.units_per_year.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={page} total={query.data.total_toys} onPageChange={setPage} disabled={query.isFetching} label="Toys pagination" />
        </>
      )}
    </section>
  )
}
