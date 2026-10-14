import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query'
import type { BomPart, Finisher, PartSource, ToyListing } from './catalog'

export type Supplier = PartSource['supplier']

export type SupplierCatalog = {
  finisher: Finisher
  suppliers: (Supplier & { connected_toys_count: number })[]
  total_suppliers: number
}

export type SupplierDetail = {
  finisher: Finisher
  supplier: Supplier
  connected_toys_count: number
  toys: ToyListing[]
}

export type SupplierParts = {
  toys: (ToyListing & { parts: BomPart[] })[]
  total_parts: number
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

export const suppliersQuery = (finisherId: string, page = 1) => queryOptions({
  queryKey: ['finishers', finisherId, 'suppliers', 'list', page],
  queryFn: ({ signal }) => get<SupplierCatalog>(
    `suppliers?${new URLSearchParams({ finisher_id: finisherId })}${page === 1 ? '' : `&page=${page}`}`, signal,
  ),
})

export const supplierDetailQuery = (finisherId: string, supplierId: string, page = 1) => queryOptions({
  queryKey: ['finishers', finisherId, 'suppliers', supplierId, 'detail', page],
  queryFn: ({ signal }) => get<SupplierDetail>(
    `suppliers/detail?${new URLSearchParams({ finisher_id: finisherId, supplier_id: supplierId })}${page === 1 ? '' : `&page=${page}`}`, signal,
  ),
})

export const supplierPartsQuery = (finisherId: string, supplierId: string) => infiniteQueryOptions({
  queryKey: ['finishers', finisherId, 'suppliers', supplierId, 'parts'],
  initialPageParam: 0,
  queryFn: ({ signal, pageParam }) => get<SupplierParts>(
    `suppliers/parts?${new URLSearchParams({ finisher_id: finisherId, supplier_id: supplierId, offset: String(pageParam) })}`, signal,
  ),
  getNextPageParam: (lastPage, _pages, offset) => {
    const next = offset + lastPage.toys.reduce((count, toy) => count + toy.parts.length, 0)
    return next < lastPage.total_parts ? next : undefined
  },
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
