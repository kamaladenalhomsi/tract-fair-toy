import { useQuery } from '@tanstack/react-query'
import { finishersQuery, type Finisher } from '../api/catalog'
import { QueryError } from './QueryError'

type Props = {
  selected: Finisher | null
  onSelect: (finisher: Finisher) => void
}

export function FinisherPicker({ selected, onSelect }: Props) {
  const query = useQuery(finishersQuery)

  return (
    <section className="finisher-picker" aria-label="Finisher selection">
      {!selected && (
        <>
          <h2>Select a Finisher</h2>
          <p>Choose an organization to view its catalog and supplier flags.</p>
        </>
      )}
      {query.isPending && <p role="status">Loading Finishers…</p>}
      {query.isError && (
        <QueryError
          message="Could not load Finishers. Check your connection and try again."
          retry={() => { void query.refetch() }}
          isFetching={query.isFetching}
        />
      )}
      {query.data && (
        query.data.finishers.length === 0 ? (
          <p role="status">No Finishers available. Import catalog data to get started.</p>
        ) : (
          <>
            <label htmlFor="finisher">{selected ? 'Switch Finisher' : 'Finisher'}</label>
            <select
              id="finisher"
              value={selected?.finisher_id ?? ''}
              onChange={(event) => {
                const finisher = query.data.finishers.find(
                  (item) => item.finisher_id === event.target.value,
                )
                if (finisher) onSelect(finisher)
              }}
            >
              <option value="" disabled>Choose a Finisher…</option>
              {query.data.finishers.map((finisher) => (
                <option key={finisher.finisher_id} value={finisher.finisher_id}>
                  {finisher.finisher_name} · {finisher.finisher_id} · {finisher.hq_country}
                </option>
              ))}
            </select>
          </>
        )
      )}
    </section>
  )
}
