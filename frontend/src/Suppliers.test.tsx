import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { toyDetailQuery, toysQuery } from './api/catalog'
import { supplierDetailQuery, suppliersQuery } from './api/suppliers'
import { uncertainty } from './test/catalogFixtures'
import { deferredResponse, json, supplierServer } from './test/supplierFixtures'

const listUrl = (finisher = 'FIN-A') => `/api/suppliers?finisher_id=${finisher}`
const detailUrl = (supplier = 'SUP-3', finisher = 'FIN-A') => `/api/suppliers/detail?finisher_id=${finisher}&supplier_id=${supplier}`
const flagUrl = (supplier = 'SUP-3', finisher = 'FIN-A') => `/api/suppliers/flag?finisher_id=${finisher}&supplier_id=${supplier}`
const overrides = new Map<string, () => Response | Promise<Response>>()
const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
let server: ReturnType<typeof supplierServer>
let client: QueryClient

function renderApp() {
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

async function selectFinisher(id = 'FIN-A') {
  fireEvent.change(await screen.findByRole('combobox'), { target: { value: id } })
}

function suppliersTab() {
  fireEvent.click(screen.getByRole('tab', { name: 'Suppliers' }))
}

async function openSupplier(id = 'SUP-3') {
  fireEvent.click(await screen.findByRole('button', { name: `Supplier ${id} ${id}` }))
}

async function startSupplier(id = 'SUP-3') {
  renderApp()
  await selectFinisher()
  suppliersTab()
  await openSupplier(id)
  await screen.findByRole('heading', { name: `Supplier ${id}` })
}

beforeEach(() => {
  server = supplierServer()
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  overrides.clear()
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (url, init) => {
    const override = overrides.get(url)
    return override ? override() : server.respond(url, init)
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  client.clear()
  vi.unstubAllGlobals()
})

describe('Supplier discovery and connection preview', () => {
  it('shows only returned suppliers and previews distinct toys and every supplier path before flagging', async () => {
    renderApp()
    await selectFinisher()
    suppliersTab()
    expect(await screen.findByRole('button', { name: 'Supplier SUP-3 SUP-3' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4)
    expect(screen.getAllByText('Not flagged')).toHaveLength(3)
    expect(screen.getByRole('columnheader', { name: 'Distinct connected toys' })).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/suppliers/detail'))).toBe(false)

    await openSupplier()
    expect(await screen.findByRole('heading', { name: 'Supplier SUP-3' })).toHaveFocus()
    expect(screen.getByText('Not flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Flag' })).toBeEnabled()
    expect(screen.getByText(/distinct connected toys —/)).toHaveTextContent('1 distinct connected toys')
    expect(screen.getByText(/distinct connected toys —/)).toHaveTextContent('not newly affected toys')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(screen.getByRole('article', { name: 'Shared train' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getAllByText(/Quantity per toy:/).map((item) => item.textContent)).toEqual([
      'Quantity per toy: 7', 'Quantity per toy: 2',
    ])
    expect(screen.getAllByText(uncertainty)).toHaveLength(1)
    for (const [part, factory] of [['PART-1', 'FAC-3'], ['PART-2', 'FAC-4'], ['PART-2', 'FAC-5']]) {
      expect(screen.getByText(`FIN-A → TOY-SHARED → ${part} → ${factory} → SUP-3`)).toBeInTheDocument()
      expect(screen.getByText(`Factory ${factory}`)).toBeInTheDocument()
    }
    expect(screen.queryByText('Factory FAC-1')).not.toBeInTheDocument()
    expect(screen.queryByText(/null|undefined/)).not.toBeInTheDocument()
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([, init]) => init?.method)).toBe(false)

    fireEvent.click(screen.getByRole('button', { name: '← Back to suppliers' }))
    expect(screen.getByRole('tab', { name: 'Suppliers' })).toHaveFocus()
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('handles supplier list loading, retryable error, and empty states', async () => {
    const pending = deferredResponse()
    overrides.set(listUrl(), () => pending.promise)
    renderApp()
    await selectFinisher()
    suppliersTab()
    expect(screen.getByRole('status')).toHaveTextContent('Loading suppliers…')
    await act(async () => { pending.resolve(new Response(null, { status: 503 })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this Finisher’s suppliers')
    overrides.set(listUrl(), () => json({ finisher: server.supplierDetail('FIN-A', 'SUP-3').finisher, suppliers: [] }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No suppliers connected/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Switch Finisher' })).toBeEnabled()
  })

  it('handles detail loading, retryable not-found error, and no connected toys', async () => {
    const pending = deferredResponse()
    overrides.set(detailUrl(), () => pending.promise)
    renderApp()
    await selectFinisher()
    suppliersTab()
    await openSupplier()
    expect(screen.getByRole('status')).toHaveTextContent('Loading supplier connections…')
    expect(screen.getByRole('button', { name: '← Back to suppliers' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Flag' })).not.toBeInTheDocument()
    await act(async () => { pending.resolve(new Response(null, { status: 404 })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this supplier’s current connections')
    overrides.set(detailUrl(), () => json({ ...server.supplierDetail('FIN-A', 'SUP-3'), connected_toys_count: 0, toys: [] }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No connected toys for this supplier/)).toBeInTheDocument()
    expect(screen.getByText(/distinct connected toys —/)).toHaveTextContent('0 distinct connected toys')
  })
})

describe('Flag mutations and query invalidation', () => {
  it('waits for server success, invalidates only A’s cached data, and refreshes list, counts, and toy traces', async () => {
    await Promise.all([
      client.prefetchQuery(toyDetailQuery('FIN-A', 'TOY-SHARED')),
      client.prefetchQuery(supplierDetailQuery('FIN-A', 'SUP-1')),
      client.prefetchQuery(toysQuery('FIN-B')),
      client.prefetchQuery(toyDetailQuery('FIN-B', 'TOY-SHARED')),
      client.prefetchQuery(suppliersQuery('FIN-B')),
      client.prefetchQuery(supplierDetailQuery('FIN-B', 'SUP-3')),
    ])
    const bRequests = fetchMock.mock.calls.filter(([url]) => url.includes('FIN-B')).length
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const pending = deferredResponse()
    overrides.set(flagUrl(), () => pending.promise)
    await startSupplier()
    fireEvent.click(screen.getByRole('button', { name: 'Flag' }))
    expect(await screen.findByText(/Saving supplier flag/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Flag' })).toBeDisabled()
    expect(screen.getByText('Not flagged by this Finisher')).toBeInTheDocument()
    expect(screen.queryByText(/successfully/)).not.toBeInTheDocument()
    expect(invalidate).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith(flagUrl(), { method: 'PUT' })

    await act(async () => { pending.resolve(server.respond(flagUrl(), { method: 'PUT' })) })
    expect(await screen.findByText('Supplier flagged successfully for Finisher FIN-A.')).toBeInTheDocument()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['finishers', 'FIN-A'] })
    expect(screen.getByRole('button', { name: 'Unflag' })).toBeEnabled()
    expect(screen.getByText('Flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getAllByText(/Flagged path —/)).toHaveLength(3)
    expect(screen.getByText(/distinct connected toys —/)).toHaveTextContent('1 distinct connected toys')
    for (const options of [toysQuery('FIN-A'), toyDetailQuery('FIN-A', 'TOY-SHARED'), suppliersQuery('FIN-A'), supplierDetailQuery('FIN-A', 'SUP-1')]) {
      expect(client.getQueryState(options.queryKey)?.isInvalidated).toBe(true)
    }
    for (const query of client.getQueryCache().findAll({ queryKey: ['finishers', 'FIN-B'] })) {
      expect(query.state.isInvalidated).toBe(false)
    }
    expect(fetchMock.mock.calls.filter(([url]) => url.includes('FIN-B'))).toHaveLength(bRequests)

    fireEvent.click(screen.getByRole('button', { name: '← Back to suppliers' }))
    const row = (await screen.findByRole('button', { name: 'Supplier SUP-3 SUP-3' })).closest('tr')!
    expect(await within(row).findByText('Flagged')).toBeInTheDocument()
    await openSupplier('SUP-1')
    expect(await screen.findByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getByText('Not flagged by this Finisher')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Toys' }))
    await waitFor(() => expect(screen.getByText(/each toy counted once/).parentElement).toHaveTextContent('2 toys · 1 potentially affected toys'))
    fireEvent.click(screen.getByRole('button', { name: 'Shared train TOY-SHARED' }))
    await waitFor(() => expect(screen.getAllByText(/Flagged path —/)).toHaveLength(3))

    suppliersTab()
    await openSupplier()
    overrides.delete(flagUrl())
    fireEvent.click(await screen.findByRole('button', { name: 'Unflag' }))
    expect(await screen.findByText('Supplier unflagged successfully for Finisher FIN-A.')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(flagUrl(), { method: 'DELETE' })
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Toys' }))
    await waitFor(() => expect(screen.getByText(/each toy counted once/).parentElement).toHaveTextContent('2 toys · 0 potentially affected toys'))
    fireEvent.click(screen.getByRole('button', { name: 'Shared train TOY-SHARED' }))
    await waitFor(() => expect(screen.getAllByText('Supplier not flagged by this Finisher')).toHaveLength(5))
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
  })

  it('restarts an uncached trace read begun before the flag commits and ignores its late stale response', async () => {
    await client.prefetchQuery(toysQuery('FIN-B'))
    const cancel = vi.spyOn(client, 'cancelQueries')
    const pendingMutation = deferredResponse()
    const pendingTrace = deferredResponse()
    const traceUrl = '/api/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED'
    const staleTrace = server.respond(traceUrl)
    overrides.set(flagUrl(), () => pendingMutation.promise)
    overrides.set(traceUrl, () => pendingTrace.promise)
    await startSupplier()
    fireEvent.click(screen.getByRole('button', { name: 'Flag' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(flagUrl(), { method: 'PUT' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Toys' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Shared train TOY-SHARED' }))
    expect(screen.getByRole('status')).toHaveTextContent('Loading toy trace…')
    const signal = fetchMock.mock.calls.find(([url]) => url === traceUrl)![1]!.signal!

    overrides.delete(traceUrl)
    await act(async () => { pendingMutation.resolve(server.respond(flagUrl(), { method: 'PUT' })) })
    expect(await screen.findByText('Potentially affected')).toBeInTheDocument()
    expect(cancel).toHaveBeenCalledWith({ queryKey: ['finishers', 'FIN-A'] })
    expect(signal.aborted).toBe(true)
    expect(fetchMock.mock.calls.filter(([url]) => url === traceUrl)).toHaveLength(2)
    expect(screen.getAllByText(/Flagged path —/)).toHaveLength(3)
    await act(async () => { pendingTrace.resolve(staleTrace) })
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getAllByText(/Flagged path —/)).toHaveLength(3)
    expect(client.getQueryState(toysQuery('FIN-B').queryKey)?.isInvalidated).toBe(false)
    expect(fetchMock.mock.calls.filter(([url]) => url.includes('FIN-B'))).toHaveLength(1)
  })

  it('unflags one supplier without clearing exposure or another flagged path', async () => {
    server.flags['FIN-A'].add('SUP-1').add('SUP-2')
    await client.prefetchQuery(toyDetailQuery('FIN-A', 'TOY-SHARED'))
    await startSupplier('SUP-1')
    fireEvent.click(screen.getByRole('button', { name: 'Unflag' }))
    expect(await screen.findByText('Supplier unflagged successfully for Finisher FIN-A.')).toBeInTheDocument()
    expect(screen.getByText('Not flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '← Back to suppliers' }))
    const supplier2 = (await screen.findByRole('button', { name: 'Supplier SUP-2 SUP-2' })).closest('tr')!
    expect(within(supplier2).getByText('Flagged')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'Toys' }))
    expect(await screen.findByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getByText(/each toy counted once/).parentElement).toHaveTextContent('2 toys · 1 potentially affected toys')
    fireEvent.click(screen.getByRole('button', { name: 'Shared train TOY-SHARED' }))
    await waitFor(() => expect(screen.getAllByText(/Flagged path —/)).toHaveLength(1))
    const remainingPath = screen.getByText(/Flagged path —/).closest('li')!
    expect(remainingPath).toHaveTextContent('FIN-A → TOY-SHARED → PART-1 → FAC-2 → SUP-2')
    expect(screen.getByText('FIN-A → TOY-SHARED → PART-1 → FAC-1 → SUP-1').closest('li')).not.toHaveClass('flagged-path')
    expect(screen.getByText(uncertainty)).toBeInTheDocument()
  })

  it.each([
    { action: 'Flag', flagged: false, network: false },
    { action: 'Unflag', flagged: true, network: false },
    { action: 'Flag', flagged: false, network: true },
  ])('surfaces $action failures (network=$network) without false success and allows retry', async ({ action, flagged, network }) => {
    if (flagged) server.flags['FIN-A'].add('SUP-3')
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    overrides.set(flagUrl(), () => {
      if (network) throw new TypeError('Failed to fetch')
      return new Response(null, { status: 503 })
    })
    await startSupplier()
    fireEvent.click(screen.getByRole('button', { name: action }))
    expect(await screen.findByRole('alert')).toHaveTextContent(`Could not ${action.toLowerCase()} this supplier`)
    expect(screen.queryByText(/successfully/)).not.toBeInTheDocument()
    expect(invalidate).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: action })).toBeEnabled()
    expect(screen.getByText(flagged ? 'Flagged by this Finisher' : 'Not flagged by this Finisher')).toBeInTheDocument()
    overrides.delete(flagUrl())
    fireEvent.click(screen.getByRole('button', { name: action }))
    expect(await screen.findByText(/successfully/)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('distinguishes a saved flag from a failed detail refresh and permits read retry', async () => {
    await startSupplier()
    overrides.set(detailUrl(), () => new Response(null, { status: 503 }))
    fireEvent.click(screen.getByRole('button', { name: 'Flag' }))
    expect(await screen.findByText('Supplier flagged successfully for Finisher FIN-A.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load this supplier’s current connections and flag status')
    expect(screen.queryByRole('button', { name: 'Flag' })).not.toBeInTheDocument()
    expect(screen.queryByText('Not flagged by this Finisher')).not.toBeInTheDocument()
    overrides.delete(detailUrl())
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('button', { name: 'Unflag' })).toBeEnabled()
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
  })
})

describe('Supplier Finisher isolation', () => {
  it('keeps a late mutation scoped to its originating Finisher after switching', async () => {
    const pending = deferredResponse()
    overrides.set(flagUrl(), () => pending.promise)
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    await startSupplier()
    fireEvent.click(screen.getByRole('button', { name: 'Flag' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(flagUrl(), { method: 'PUT' }))
    await selectFinisher('FIN-B')
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveAttribute('aria-selected', 'true')
    suppliersTab()
    await openSupplier()
    expect(await screen.findByText('Not flagged by this Finisher')).toBeInTheDocument()
    await act(async () => { pending.resolve(server.respond(flagUrl(), { method: 'PUT' })) })
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['finishers', 'FIN-A'] }))
    expect(screen.queryByText(/successfully|Saving supplier flag/)).not.toBeInTheDocument()
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
    expect(screen.queryByText('Flagged by this Finisher')).not.toBeInTheDocument()
    expect(screen.getByText('Not flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByText('FIN-B → TOY-SHARED → PART-1 → FAC-3 → SUP-3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Flag' })).toBeEnabled()
    expect(server.flags['FIN-B'].size).toBe(0)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method)).toHaveLength(1)

    await selectFinisher('FIN-A')
    suppliersTab()
    await openSupplier()
    expect(await screen.findByText('Flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Unflag' })).toBeEnabled()
    expect(screen.queryByText(/successfully/)).not.toBeInTheDocument()
    await selectFinisher('FIN-B')
    suppliersTab()
    await openSupplier()
    expect(await screen.findByText('Not flagged by this Finisher')).toBeInTheDocument()
  })

  it.each(['list', 'detail'])('cancels pending A supplier %s requests and ignores late flags while B loads', async (kind) => {
    server.flags['FIN-A'].add('SUP-3')
    const pendingA = deferredResponse()
    const pendingB = deferredResponse()
    const urlA = kind === 'list' ? listUrl() : detailUrl()
    const urlB = kind === 'list' ? listUrl('FIN-B') : detailUrl('SUP-3', 'FIN-B')
    overrides.set(urlA, () => pendingA.promise)
    overrides.set(urlB, () => pendingB.promise)
    renderApp()
    await selectFinisher()
    suppliersTab()
    if (kind === 'detail') await openSupplier()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(urlA, expect.anything()))
    const signal = fetchMock.mock.calls.find(([url]) => url === urlA)![1]!.signal!
    await selectFinisher('FIN-B')
    expect(signal.aborted).toBe(true)
    suppliersTab()
    if (kind === 'detail') await openSupplier()
    expect(screen.getByRole('status')).toHaveTextContent(kind === 'list' ? 'Loading suppliers…' : 'Loading supplier connections…')
    expect(screen.queryByText(/Flagged by this Finisher|Flagged path —/)).not.toBeInTheDocument()
    await act(async () => { pendingA.resolve(server.respond(urlA)) })
    expect(screen.queryByText(/Flagged by this Finisher|Flagged path —/)).not.toBeInTheDocument()
    await act(async () => { pendingB.resolve(server.respond(urlB)) })
    if (kind === 'list') await openSupplier()
    expect(await screen.findByText('Not flagged by this Finisher')).toBeInTheDocument()
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
  })
})
