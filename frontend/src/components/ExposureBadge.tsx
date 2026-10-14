import type { ExposureStatus } from '../api/catalog'

export function ExposureBadge({ status }: { status: ExposureStatus }) {
  return (
    <span className={`exposure-badge ${status === 'Potentially affected' ? 'affected' : 'unflagged'}`}>
      {status}
    </span>
  )
}
