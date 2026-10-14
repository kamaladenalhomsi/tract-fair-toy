type Props = {
  page: number
  total: number
  onPageChange: (page: number) => void
  disabled?: boolean
  label: string
}

export function Pagination({ page, total, onPageChange, disabled, label }: Props) {
  const pages = Math.max(1, Math.ceil(total / 10))
  return (
    <nav className="pagination" aria-label={label}>
      <span>{total === 0 ? 0 : (page - 1) * 10 + 1}–{Math.min(page * 10, total)} of {total}</span>
      <button type="button" disabled={disabled || page === 1} onClick={() => onPageChange(page - 1)}>Previous</button>
      {Array.from({ length: pages }, (_, index) => (
        <button type="button" key={index + 1} aria-label={`Page ${index + 1}`}
          aria-current={page === index + 1 ? 'page' : undefined}
          disabled={disabled || page === index + 1} onClick={() => onPageChange(index + 1)}>{index + 1}</button>
      ))}
      <span>Page {page} of {pages}</span>
      <button type="button" disabled={disabled || page >= pages} onClick={() => onPageChange(page + 1)}>Next</button>
    </nav>
  )
}
