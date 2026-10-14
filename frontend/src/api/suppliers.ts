import { queryOptions } from '@tanstack/react-query'
import type { BomPart, Finisher, PartSource, ToyListing } from './catalog'

export type Supplier = PartSource['supplier']

export type SupplierCatalog = {
  finisher: Finisher
  suppliers: (Supplier & { connected_toys_count: number })[]
}

export type SupplierDetail = {
  finisher: Finisher
  supplier: Supplier
  connected_toys_count: number
  toys: (ToyListing & { parts: BomPart[] })[]
}

export type SupplierFlag = {
  finisher_id: string
  supplier_id: string
  is_flagged: boolean
}

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, { signal })
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json() as Promise<T>
}

export const suppliersQuery = (finisherId: string) => queryOptions({
  queryKey: ['finishers', finisherId, 'suppliers'],
  queryFn: ({ signal }) => get<SupplierCatalog>(
    `suppliers?${new URLSearchParams({ finisher_id: finisherId })}`, signal,
  ),
})

export const supplierDetailQuery = (finisherId: string, supplierId: string) => queryOptions({
  queryKey: ['finishers', finisherId, 'suppliers', supplierId],
  queryFn: ({ signal }) => get<SupplierDetail>(
    `suppliers/detail?${new URLSearchParams({ finisher_id: finisherId, supplier_id: supplierId })}`, signal,
  ),
})

export async function setSupplierFlag(
  finisherId: string, supplierId: string, isFlagged: boolean,
): Promise<SupplierFlag> {
  const params = new URLSearchParams({ finisher_id: finisherId, supplier_id: supplierId })
  const response = await fetch(`/api/suppliers/flag?${params}`, {
    method: isFlagged ? 'PUT' : 'DELETE',
  })
  if (!response.ok) throw new Error(`Supplier flag update failed (${response.status})`)
  return response.json() as Promise<SupplierFlag>
}
