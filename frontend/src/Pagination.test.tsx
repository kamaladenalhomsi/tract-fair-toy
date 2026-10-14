import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { ToysList } from './components/ToysList'
import { SuppliersList } from './components/SuppliersList'
import { ToyDetails } from './components/ToyDetails'
import { SupplierDetails } from './components/SupplierDetails'
import { detailA, finisherA } from './test/catalogFixtures'
import { toyDetailQuery } from './api/catalog'
import { deferredResponse, json } from './test/supplierFixtures'

const toys = Array.from({ length: 21 }, (_, i) => ({ ...detailA, toy_id: `TOY-${i}`, toy_name: `Toy ${i}` }))
const parts = Array.from({ length: 21 }, (_, i) => ({ ...detailA.parts[0], part_id: `PART-${i}`, part_name: `Part ${i}` }))
const suppliers = Array.from({ length: 21 }, (_, i) => ({
  ...detailA.parts[0].sources[0].supplier, supplier_id: `SUP-${i}`, supplier_name: `Supplier ${i}`,
  is_flagged: false, connected_toys_count: 21,
}))
const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
let client: QueryClient
let failMore: boolean
let flagged: boolean

function respond(url: string) {
  const { pathname, searchParams } = new URL(url, 'http://localhost')
  const start = (Number(searchParams.get('page') ?? 1) - 1) * 10
  const offset = Number(searchParams.get('offset') ?? 0)
  if (offset === 20 && failMore) return new Response(null, { status: 503 })
  switch (pathname) {
    case '/api/toys': return json({ finisher: finisherA, toys: toys.slice(start, start + 10), total_toys: 21, potentially_affected_toys: 21 })
    case '/api/suppliers': return json({ finisher: finisherA, suppliers: suppliers.slice(start, start + 10).map((supplier) => ({ ...supplier, is_flagged: flagged })), total_suppliers: 21 })
    case '/api/toys/detail': return json({ ...detailA, parts: parts.slice(offset, offset + 10), total_parts: 21 })
    case '/api/suppliers/detail': return json({ finisher: finisherA, supplier: suppliers[0], toys: toys.slice(start, start + 10), connected_toys_count: 21 })
    case '/api/suppliers/parts': return json({ toys: [{ ...toys[0], parts: parts.slice(offset, offset + 10) }], total_parts: 21 })
    default: throw new Error(`Unexpected request ${url}`)
  }
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  failMore = false
  flagged = false
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (url) => respond(url))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  client.clear()
  vi.unstubAllGlobals()
})

it.each(['toys', 'suppliers'])('paginates %s on the server and keeps totals global', async (kind) => {
  render(<QueryClientProvider client={client}>
    {kind === 'toys' ? <ToysList finisherId="FIN-A" onSelect={vi.fn()} /> : <SuppliersList finisherId="FIN-A" onSelect={vi.fn()} />}
  </QueryClientProvider>)
  expect(await screen.findAllByRole('row')).toHaveLength(11)
  expect(screen.getByText('1–10 of 21')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('11–20 of 21')).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(11)
  expect(fetchMock.mock.calls.some(([url]) => url === `/api/${kind}?finisher_id=FIN-A&page=2`)).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Page 3' }))
  expect(await screen.findByText('21–21 of 21')).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(2)
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  if (kind === 'toys') expect(screen.getByText(/each toy counted once/).parentElement).toHaveTextContent('21 toys · 21 potentially affected toys')
  else expect(within(screen.getAllByRole('row')[1]).getByText('21')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Previous' }))
  expect(await screen.findByText('11–20 of 21')).toBeInTheDocument()
})

it.each(['toy', 'supplier'])('loads %s parts 10 at a time and preserves loaded paths on failure and retry', async (kind) => {
  render(<QueryClientProvider client={client}>
    {kind === 'toy' ? <ToyDetails finisherId="FIN-A" toyId="TOY-SHARED" onBack={vi.fn()} /> : <SupplierDetails finisherId="FIN-A" supplierId="SUP-0" onBack={vi.fn()} />}
  </QueryClientProvider>)
  await screen.findByRole('button', { name: 'Load more' })
  expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(10)
  expect(screen.getAllByRole('listitem')).toHaveLength(30)
  expect(screen.queryByText('Part 10')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(20))
  expect(screen.getByText(/21 .*total · 20 loaded/)).toBeInTheDocument()
  failMore = true
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load more parts')
  expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(20)
  failMore = false
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(21))
  expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  expect(screen.getAllByRole('listitem')).toHaveLength(63)
  expect(screen.getByText(/21 .*total · 21 loaded/)).toBeInTheDocument()
})

it('keeps supplier parts independent of the connected-toys table page', async () => {
  render(<QueryClientProvider client={client}><SupplierDetails finisherId="FIN-A" supplierId="SUP-0" onBack={vi.fn()} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(20))
  const requests = fetchMock.mock.calls.filter(([url]) => url.includes('/suppliers/parts')).length
  fireEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(await screen.findByText('11–20 of 21')).toBeInTheDocument()
  expect(screen.getAllByRole('row')).toHaveLength(11)
  expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(20)
  expect(screen.getByText(/distinct connected toys —/)).toHaveTextContent('21 distinct connected toys')
  expect(fetchMock.mock.calls.filter(([url]) => url.includes('/suppliers/parts'))).toHaveLength(requests)
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(21))
  expect(screen.getByText('11–20 of 21')).toBeInTheDocument()
})

it('flags and unflags from a supplier row only after confirmation, invalidates its Finisher, and permits retry', async () => {
  const pending = deferredResponse()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  fetchMock.mockImplementation(async (url, init) => init?.method ? pending.promise : respond(url))
  render(<QueryClientProvider client={client}><SuppliersList finisherId="FIN-A" onSelect={vi.fn()} /></QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Flag Supplier 0' }))
  expect(await screen.findByText(/Saving supplier flag/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Flag Supplier 0' })).toBeDisabled()
  expect(invalidate).not.toHaveBeenCalled()
  expect(screen.queryByText(/successfully/)).not.toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith('/api/suppliers/flag?finisher_id=FIN-A&supplier_id=SUP-0', { method: 'PUT' })
  flagged = true
  await act(async () => { pending.resolve(json({ finisher_id: 'FIN-A', supplier_id: 'SUP-0', is_flagged: true })) })
  expect(await screen.findByText(/SUP-0 flagged successfully/)).toBeInTheDocument()
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['finishers', 'FIN-A'] })
  fetchMock.mockImplementation(async (url, init) => init?.method ? new Response(null, { status: 503 }) : respond(url))
  fireEvent.click(screen.getByRole('button', { name: 'Unflag Supplier 0' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not update supplier flag')
  expect(screen.queryByText(/successfully/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Unflag Supplier 0' })).toBeEnabled()
  fetchMock.mockImplementation(async (url, init) => {
    if (!init?.method) return respond(url)
    flagged = false
    return json({ finisher_id: 'FIN-A', supplier_id: 'SUP-0', is_flagged: false })
  })
  fireEvent.click(screen.getByRole('button', { name: 'Unflag Supplier 0' }))
  expect(await screen.findByText(/SUP-0 unflagged successfully/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Flag Supplier 0' })).toBeEnabled()
})

it('cancels in-flight Load more and refreshes every loaded page after flagging reorders parts', async () => {
  const pending = deferredResponse()
  let holdMore = true
  let staleResponse: Response
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method) {
      flagged = true
      return json({ finisher_id: 'FIN-A', supplier_id: 'SUP-0', is_flagged: true })
    }
    const { pathname, searchParams } = new URL(url, 'http://localhost')
    if (pathname !== '/api/toys/detail') return respond(url)
    const offset = Number(searchParams.get('offset') ?? 0)
    const affected = flagged && searchParams.get('finisher_id') === 'FIN-A'
    const ordered = affected ? [parts[20], ...parts.slice(0, 20)] : parts
    const response = json({ ...detailA, total_parts: 21, parts: ordered.slice(offset, offset + 10) })
    if (offset === 20 && holdMore) {
      staleResponse = response
      return pending.promise
    }
    return response
  })
  const bOptions = toyDetailQuery('FIN-B', 'TOY-SHARED')
  await client.prefetchInfiniteQuery({ ...bOptions, pages: 2 })
  const bData = client.getQueryData(bOptions.queryKey)
  render(<QueryClientProvider client={client}>
    <SuppliersList finisherId="FIN-A" onSelect={vi.fn()} />
    <ToyDetails finisherId="FIN-A" toyId="TOY-SHARED" onBack={vi.fn()} />
  </QueryClientProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByText(/Quantity per toy:/)).toHaveLength(20))
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await screen.findByRole('button', { name: 'Loading more…' })
  const signal = fetchMock.mock.calls.find(([url]) => url.includes('FIN-A') && url.includes('offset=20'))![1]!.signal!
  fireEvent.click(screen.getByRole('button', { name: 'Flag Supplier 0' }))
  await screen.findByText(/SUP-0 flagged successfully/)
  expect(signal.aborted).toBe(true)
  expect(screen.getAllByRole('article').map((article) => within(article).getByRole('heading').textContent)).toEqual([
    'Part 20', ...Array.from({ length: 19 }, (_, i) => `Part ${i}`),
  ])
  expect(screen.getAllByRole('listitem')).toHaveLength(60)
  expect(screen.getByText('21 parts total · 20 loaded')).toBeInTheDocument()
  expect(client.getQueryData(bOptions.queryKey)).toBe(bData)
  expect(client.getQueryState(bOptions.queryKey)?.isInvalidated).toBe(false)
  await act(async () => { pending.resolve(staleResponse) })
  expect(screen.queryByRole('article', { name: 'Part 19' })).not.toBeInTheDocument()
  holdMore = false
  fireEvent.click(screen.getByRole('button', { name: 'Load more' }))
  await waitFor(() => expect(screen.getAllByRole('article')).toHaveLength(21))
  expect(screen.getAllByRole('article', { name: 'Part 20' })).toHaveLength(1)
  expect(screen.getAllByRole('listitem')).toHaveLength(63)
})
