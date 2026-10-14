type Props = {
  message: string
  retry: () => void
  isFetching: boolean
}

export function QueryError({ message, retry, isFetching }: Props) {
  return (
    <div className="error-state" role="alert">
      <p>{message}</p>
      <button type="button" onClick={retry} disabled={isFetching}>
        {isFetching ? 'Retrying…' : 'Try again'}
      </button>
    </div>
  )
}
