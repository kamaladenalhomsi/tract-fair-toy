import { useQuery } from '@tanstack/react-query'
import { suppliersQuery } from '../api/suppliers'
import { QueryError } from './QueryError'

type Props = {
  finisherId: string
  onSelect: (supplierId: string) => void
}

export function SuppliersList({ finisherId, onSelect }: Props) {
  const query = useQuery(suppliersQuery(finisherId))

  return (
    <section aria-labelledby="suppliers-heading">
      <h2 id="suppliers-heading">Suppliers</h2>
      <p>Only suppliers potentially connected to this Finisher’s toys are listed.
        Select a supplier to inspect connections before flagging.</p>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  )
}
