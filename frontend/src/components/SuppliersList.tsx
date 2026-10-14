import { useState } from 'react'
import { Pagination } from './Pagination'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { setSupplierFlag, suppliersQuery } from '../api/suppliers'
import { QueryError } from './QueryError'

type Props = {
  finisherId: string
  onSelect: (supplierId: string) => void
}

export function SuppliersList({ finisherId, onSelect }: Props) {
  const [page, setPage] = useState(1)
  const query = useQuery(suppliersQuery(finisherId, page))
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ supplierId, isFlagged }: { supplierId: string, isFlagged: boolean }) =>
      setSupplierFlag(finisherId, supplierId, isFlagged),
    onSuccess: async (result) => {
      const scope = { queryKey: ['finishers', result.finisher_id] }
      await client.cancelQueries(scope)
      await client.invalidateQueries(scope)
    },
  })

  return (
    <section aria-labelledby="suppliers-heading">
      <h2 id="suppliers-heading">Suppliers</h2>
      <p>Only suppliers potentially connected to this Finisher’s toys are listed.
        Select a supplier to inspect connections before flagging.</p>
      {mutation.isPending && <p role="status">Saving supplier flag and refreshing this Finisher’s data…</p>}
      {mutation.isSuccess && <p role="status" className="mutation-success">Supplier {mutation.data.supplier_id} {mutation.data.is_flagged ? 'flagged' : 'unflagged'} successfully for Finisher {finisherId}.</p>}
      {mutation.isError && <p role="alert" className="error-state">Could not update supplier flag. {mutation.error.message}. Try the action again.</p>}
      {query.isPending && <p role="status">Loading suppliers…</p>}
      {query.isError && (
        <QueryError
          message="Could not load this Finisher’s suppliers. Try again or switch Finisher."
          retry={() => { void query.refetch() }}
          isFetching={query.isFetching}
        />
      )}
      {query.isSuccess && (query.data.suppliers.length === 0 ? (
        <p role="status">No suppliers connected to this Finisher’s toys. Choose another Finisher to explore.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <caption className="sr-only">Suppliers connected to the selected Finisher’s toys</caption>
            <thead>
              <tr>
                <th scope="col">Supplier</th>
                <th scope="col">HQ country</th>
                <th scope="col">Flag status for this Finisher</th>
                <th scope="col">Distinct connected toys</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {query.data.suppliers.map((supplier) => (
                <tr key={supplier.supplier_id}>
                  <th scope="row">
                    <button className="text-button" onClick={() => onSelect(supplier.supplier_id)}>
                      {supplier.supplier_name}{' '}
                      <span className="record-id">{supplier.supplier_id}</span>
                    </button>
                  </th>
                  <td>{supplier.hq_country}</td>
                  <td>
                    <span className={`exposure-badge ${supplier.is_flagged ? 'affected' : 'unflagged'}`}>
                      {supplier.is_flagged ? 'Flagged' : 'Not flagged'}
                    </span>
                  </td>
                  <td>{supplier.connected_toys_count}</td>
                  <td><button type="button" disabled={mutation.isPending || query.isFetching}
                    aria-label={`${supplier.is_flagged ? 'Unflag' : 'Flag'} ${supplier.supplier_name}`}
                    onClick={() => mutation.mutate({ supplierId: supplier.supplier_id, isFlagged: !supplier.is_flagged })}
                  >{supplier.is_flagged ? 'Unflag' : 'Flag'}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      {query.isSuccess && <Pagination page={page} total={query.data.total_suppliers} onPageChange={setPage} disabled={query.isFetching || mutation.isPending} label="Suppliers pagination" />}
    </section>
  )
}
