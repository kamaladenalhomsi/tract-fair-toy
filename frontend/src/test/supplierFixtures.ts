import type { ToyCatalog, ToyDetail } from '../api/catalog'
import type { SupplierCatalog, SupplierDetail } from '../api/suppliers'
import { catalogA, catalogB, detailA, detailB, finisherA, finisherB } from './catalogFixtures'

export function json(value: unknown) {
  return new Response(JSON.stringify(value), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  })
}

export function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => { resolve = done })
  return { promise, resolve }
}

export function supplierServer() {
  const flags: Record<string, Set<string>> = { 'FIN-A': new Set(), 'FIN-B': new Set() }

  function toyDetail(finisherId: string): ToyDetail {
    const base = finisherId === 'FIN-A' ? detailA : detailB
    const parts = base.parts.map((part) => ({
      ...part,
      sources: part.sources.map((source) => ({
        ...source,
        supplier: { ...source.supplier, is_flagged: flags[finisherId].has(source.supplier.supplier_id) },
      })),
    }))
    return {
      ...base, parts,
      exposure_status: parts.some((part) => part.sources.some((source) => source.supplier.is_flagged))
        ? 'Potentially affected' : 'No flagged supplier found',
    }
  }

  function toyCatalog(finisherId: string): ToyCatalog {
    const base = finisherId === 'FIN-A' ? catalogA : catalogB
    const toys = base.toys.map((toy) => toy.toy_id === 'TOY-SHARED' ? toyDetail(finisherId) : toy)
    return {
      ...base, toys,
      potentially_affected_toys: toys.filter((toy) => toy.exposure_status === 'Potentially affected').length,
    }
  }

  function supplierCatalog(finisherId: string): SupplierCatalog {
    const detail = toyDetail(finisherId)
    const suppliers = new Map(detail.parts.flatMap((part) => part.sources.map((source) => [
      source.supplier.supplier_id, { ...source.supplier, connected_toys_count: 1 },
    ] as const)))
    return { finisher: detail.finisher, suppliers: [...suppliers.values()] }
  }

  function supplierDetail(finisherId: string, supplierId: string): SupplierDetail {
    const toy = toyDetail(finisherId)
    return {
      finisher: toy.finisher,
      supplier: supplierCatalog(finisherId).suppliers.find((supplier) => supplier.supplier_id === supplierId)!,
      connected_toys_count: 1,
      toys: [{
        ...toy,
        parts: toy.parts.map((part) => ({
          ...part, sources: part.sources.filter((source) => source.supplier.supplier_id === supplierId),
        })).filter((part) => part.sources.length > 0),
      }],
    }
  }

  function respond(url: string, init?: RequestInit): Response {
    const { pathname, searchParams } = new URL(url, 'http://localhost')
    const finisherId = searchParams.get('finisher_id')!
    const supplierId = searchParams.get('supplier_id')!
    switch (pathname) {
      case '/api/finishers': return json({ finishers: [finisherA, finisherB] })
      case '/api/toys': return json(toyCatalog(finisherId))
      case '/api/toys/detail': return json(toyDetail(finisherId))
      case '/api/suppliers': return json(supplierCatalog(finisherId))
      case '/api/suppliers/detail': return json(supplierDetail(finisherId, supplierId))
      case '/api/suppliers/flag': {
        if (init?.method === 'PUT') flags[finisherId].add(supplierId)
        else if (init?.method === 'DELETE') flags[finisherId].delete(supplierId)
        else throw new Error(`Unexpected mutation method: ${init?.method}`)
        return json({ finisher_id: finisherId, supplier_id: supplierId, is_flagged: flags[finisherId].has(supplierId) })
      }
      default: throw new Error(`Unexpected request: ${url}`)
    }
  }

  return { flags, respond, supplierDetail }
}
