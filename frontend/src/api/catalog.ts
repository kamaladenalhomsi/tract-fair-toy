import { queryOptions } from '@tanstack/react-query'

export type Finisher = {
  finisher_id: string
  finisher_name: string
  hq_country: string
}

export type ExposureStatus = 'Potentially affected' | 'No flagged supplier found'

export type ToyListing = {
  toy_id: string
  toy_name: string
  retail_price_usd: string
  units_per_year: number
  exposure_status: ExposureStatus
}

export type ToyCatalog = {
  finisher: Finisher
  toys: ToyListing[]
  total_toys: number
  potentially_affected_toys: number
}

export type PartSource = {
  unit_cost_usd: string
  factory: {
    factory_id: string
    factory_name: string
    address_line: string | null
    city: string | null
    country: string
  }
  supplier: {
    supplier_id: string
    supplier_name: string
    hq_country: string
    is_flagged: boolean
  }
}

export type BomPart = {
  part_id: string
  part_name: string
  quantity: number
  distinct_supplier_count: number
  source_uncertainty: string | null
  sources: PartSource[]
}

export type ToyDetail = ToyListing & {
  finisher: Finisher
  parts: BomPart[]
}

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, { signal })
  if (!response.ok) {
    throw new Error(`Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const finishersQuery = queryOptions({
  queryKey: ['finishers'],
  queryFn: ({ signal }) => get<{ finishers: Finisher[] }>('finishers', signal),
})

export const toysQuery = (finisherId: string) => queryOptions({
  queryKey: ['finishers', finisherId, 'toys'],
  queryFn: ({ signal }) => get<ToyCatalog>(
    `toys?${new URLSearchParams({ finisher_id: finisherId })}`, signal,
  ),
})

export const toyDetailQuery = (finisherId: string, toyId: string) => queryOptions({
  queryKey: ['finishers', finisherId, 'toys', toyId],
  queryFn: ({ signal }) => get<ToyDetail>(
    `toys/detail?${new URLSearchParams({ finisher_id: finisherId, toy_id: toyId })}`, signal,
  ),
})
