import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  catalogA, catalogB, detailA, detailB, finisherA, finisherB, uncertainty,
} from './test/catalogFixtures'

const finishersUrl = '/api/finishers'
const toysAUrl = '/api/toys?finisher_id=FIN-A'
const toysBUrl = '/api/toys?finisher_id=FIN-B'
const detailAUrl = '/api/toys/detail?finisher_id=FIN-A&toy_id=TOY-SHARED'
const detailBUrl = '/api/toys/detail?finisher_id=FIN-B&toy_id=TOY-SHARED'
const handlers = new Map<string, () => Response | Promise<Response>>()
const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
const clients: QueryClient[] = []

function json(value: unknown) {
  return new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

function deferredResponse() {
  let resolve!: (response: Response) => void
  const promise = new Promise<Response>((done) => { resolve = done })
  return { promise, resolve }
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  clients.push(client)
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

async function selectFinisher(id = 'FIN-A') {
  fireEvent.change(await screen.findByRole('combobox'), { target: { value: id } })
}

async function openSharedToy() {
  fireEvent.click(await screen.findByRole('button', { name: 'Shared train TOY-SHARED' }))
}

beforeEach(() => {
  handlers.clear()
  handlers.set(finishersUrl, () => json({ finishers: [finisherA, finisherB] }))
  handlers.set(toysAUrl, () => json(catalogA))
  handlers.set(toysBUrl, () => json(catalogB))
  handlers.set(detailAUrl, () => json(detailA))
  handlers.set(detailBUrl, () => json(detailB))
  handlers.set('/api/suppliers?finisher_id=FIN-A', () => json({ finisher: finisherA, suppliers: [], total_suppliers: 0 }))
  fetchMock.mockReset()
  fetchMock.mockImplementation(async (url) => {
    const handler = handlers.get(url)
    if (!handler) throw new Error(`Unexpected request: ${url}`)
    return handler()
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  clients.forEach((client) => client.clear())
  clients.length = 0
  vi.unstubAllGlobals()
})

describe('Finisher selection and workspace', () => {
  it('requires explicit selection on each launch before fetching a catalog', async () => {
    const view = renderApp()
    expect(screen.getByRole('heading', { name: 'FairToy' })).toBeInTheDocument()
    expect(await screen.findByRole('combobox', { name: 'Finisher' })).toHaveValue('')
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([finishersUrl])

    await selectFinisher()
    expect(await screen.findByRole('button', { name: 'Shared train TOY-SHARED' })).toBeInTheDocument()
    expect(screen.getByText(/Selected Finisher:/)).toHaveTextContent('Alpha Toys')
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('combobox', { name: 'Switch Finisher' })).toHaveValue('FIN-A')

    view.unmount()
    renderApp()
    expect(await screen.findByRole('combobox', { name: 'Finisher' })).toHaveValue('')
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('shows loading, error with retry, and empty Finisher states', async () => {
    const pending = deferredResponse()
    handlers.set(finishersUrl, () => pending.promise)
    renderApp()
    expect(screen.getByRole('status')).toHaveTextContent('Loading Finishers…')
    await act(async () => { pending.resolve(new Response(null, { status: 503 })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load Finishers')
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()

    handlers.set(finishersUrl, () => json({ finishers: [] }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No Finishers available/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('opens Suppliers with keyboard tabs and resets to Toys on switching', async () => {
    renderApp()
    await selectFinisher()
    const toysTab = screen.getByRole('tab', { name: 'Toys' })
    toysTab.focus()
    fireEvent.keyDown(toysTab, { key: 'ArrowRight' })
    expect(screen.getByRole('tab', { name: 'Suppliers' })).toHaveFocus()
    expect(await screen.findByText(/No suppliers connected to this Finisher’s toys/)).toBeInTheDocument()
    expect(screen.getByRole('tabpanel', { name: 'Suppliers' })).toBeInTheDocument()

    fireEvent.keyDown(screen.getByRole('tab', { name: 'Suppliers' }), { key: 'Home' })
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Suppliers' }))
    await selectFinisher('FIN-B')
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('31.00')).toBeInTheDocument()
  })
})

describe('Toys catalog and traceability', () => {
  it('lists server-computed statuses and distinct affected counts without implying safety', async () => {
    renderApp()
    await selectFinisher()
    expect(await screen.findByRole('button', { name: 'Shared train TOY-SHARED' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Wooden blocks TOY-OTHER' })).toBeInTheDocument()
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
    expect(screen.getByText(/each toy counted once/).parentElement).toHaveTextContent('2 toys · 1 potentially affected toys')
    expect(screen.getByText(/Flags apply only/)).toHaveTextContent('not that the toy or its suppliers are verified safe')
    expect(screen.getByText('24.50')).toBeInTheDocument()
    expect(screen.getByText((1200).toLocaleString())).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => url.includes('/detail'))).toBe(false)
  })

  it('shows every source path, highlights both flagged paths, and preserves per-part quantities', async () => {
    renderApp()
    await selectFinisher()
    await openSharedToy()
    expect(await screen.findByRole('heading', { name: 'Shared train' })).toHaveFocus()
    expect(screen.getByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getByText(uncertainty)).toBeInTheDocument()
    expect(screen.getByText(/An unflagged alternate source/)).toBeInTheDocument()

    const wheel = screen.getByRole('article', { name: 'Wheel' })
    const axle = screen.getByRole('article', { name: 'Axle' })
    expect(within(wheel).getByText(/Quantity per toy:/)).toHaveTextContent('Quantity per toy: 7')
    expect(within(axle).getByText(/Quantity per toy:/)).toHaveTextContent('Quantity per toy: 2')
    expect(within(wheel).getAllByRole('listitem')).toHaveLength(3)
    expect(within(axle).getAllByRole('listitem')).toHaveLength(2)
    expect(within(axle).queryByText(uncertainty)).not.toBeInTheDocument()
    const flagged = screen.getAllByText('Flagged path — supplier flagged by this Finisher')
    expect(flagged).toHaveLength(2)
    flagged.forEach((status) => expect(status.closest('li')).toHaveClass('flagged-path'))
    expect(screen.getAllByText('Supplier not flagged by this Finisher')).toHaveLength(3)

    for (const part of detailA.parts) {
      for (const source of part.sources) {
        expect(screen.getByText(`FIN-A → TOY-SHARED → ${part.part_id} → ${source.factory.factory_id} → ${source.supplier.supplier_id}`)).toBeInTheDocument()
        expect(screen.getByText(source.factory.factory_name)).toBeInTheDocument()
      }
    }
    expect(screen.getByText('Supplier SUP-1')).toBeInTheDocument()
    expect(screen.getByText('Supplier SUP-2')).toBeInTheDocument()
    expect(screen.getAllByText('Supplier SUP-3')).toHaveLength(3)
    expect(screen.queryByText(/null|undefined/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '← Back to toys' }))
    expect(screen.getByRole('tab', { name: 'Toys' })).toHaveFocus()
    expect(await screen.findByRole('heading', { name: 'Toy catalog' })).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: 'Wheel' })).not.toBeInTheDocument()
  })

  it('shows catalog loading, retryable errors, and an empty catalog with switching available', async () => {
    const pending = deferredResponse()
    handlers.set(toysAUrl, () => pending.promise)
    renderApp()
    await selectFinisher()
    expect(screen.getByRole('status')).toHaveTextContent('Loading toys…')
    await act(async () => { pending.resolve(new Response(null, { status: 500 })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this Finisher’s toys')
    handlers.set(toysAUrl, () => json({ ...catalogA, toys: [], total_toys: 0, potentially_affected_toys: 0 }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText(/No toys in this Finisher’s catalog/)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Switch Finisher' })).toBeEnabled()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('handles network failures and recovers on catalog retry', async () => {
    handlers.set(toysAUrl, () => { throw new TypeError('Failed to fetch') })
    renderApp()
    await selectFinisher()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    handlers.set(toysAUrl, () => json(catalogA))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('24.50')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows detail loading, retryable not-found errors, and missing BOM state', async () => {
    const pending = deferredResponse()
    handlers.set(detailAUrl, () => pending.promise)
    renderApp()
    await selectFinisher()
    await openSharedToy()
    expect(screen.getByRole('status')).toHaveTextContent('Loading toy trace…')
    expect(screen.getByRole('button', { name: '← Back to toys' })).toBeEnabled()
    await act(async () => { pending.resolve(new Response(null, { status: 404 })) })
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load this toy’s trace')
    handlers.set(detailAUrl, () => json({ ...detailA, parts: [] }))
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('No BOM parts recorded for this toy.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '← Back to toys' }))
    expect(await screen.findByRole('heading', { name: 'Toy catalog' })).toBeInTheDocument()
  })

  it('preserves accessible part names when authoritative IDs contain whitespace', async () => {
    handlers.set(detailAUrl, () => json({
      ...detailA, parts: [{ ...detailA.parts[0], part_id: 'PART 1 / & 2' }],
    }))
    renderApp()
    await selectFinisher()
    await openSharedToy()
    const part = await screen.findByRole('article', { name: 'Wheel' })
    expect(within(part).getByText('PART 1 / & 2')).toBeInTheDocument()
    expect(within(part).getByText('FIN-A → TOY-SHARED → PART 1 / & 2 → FAC-1 → SUP-1')).toBeInTheDocument()
  })

  it('handles a BOM part without listed sources', async () => {
    handlers.set(detailAUrl, () => json({
      ...detailA,
      exposure_status: 'No flagged supplier found',
      parts: [{ ...detailA.parts[0], sources: [], distinct_supplier_count: 0, source_uncertainty: null }],
    }))
    renderApp()
    await selectFinisher()
    await openSharedToy()
    expect(await screen.findByText('No listed manufacturing sources for this part.')).toBeInTheDocument()
    expect(screen.getByText(/Quantity per toy:/)).toHaveTextContent('7')
    expect(screen.queryByText(uncertainty)).not.toBeInTheDocument()
  })
})

describe('Finisher isolation', () => {
  it('never displays A’s flags or listing data while B’s shared-toy catalog and trace load', async () => {
    const pendingCatalog = deferredResponse()
    const pendingDetail = deferredResponse()
    handlers.set(toysBUrl, () => pendingCatalog.promise)
    handlers.set(detailBUrl, () => pendingDetail.promise)
    renderApp()
    await selectFinisher()
    await openSharedToy()
    expect(await screen.findByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getAllByText(/Flagged path —/)).toHaveLength(2)

    await selectFinisher('FIN-B')
    expect(screen.getByText(/Selected Finisher:/)).toHaveTextContent('Beta Toys')
    expect(screen.getByRole('status')).toHaveTextContent('Loading toys…')
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
    expect(screen.queryByText('24.50')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '← Back to toys' })).not.toBeInTheDocument()
    await act(async () => { pendingCatalog.resolve(json(catalogB)) })
    expect(await screen.findByText('31.00')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Wooden blocks TOY-OTHER' })).not.toBeInTheDocument()

    await openSharedToy()
    expect(screen.getByRole('status')).toHaveTextContent('Loading toy trace…')
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
    await act(async () => { pendingDetail.resolve(json(detailB)) })
    expect(await screen.findByRole('heading', { name: 'Shared train' })).toBeInTheDocument()
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
    expect(screen.getByText('FIN-B → TOY-SHARED → PART-1 → FAC-1 → SUP-1')).toBeInTheDocument()
    expect(screen.getByText('31.00')).toBeInTheDocument()
    expect(screen.getByText('800')).toBeInTheDocument()

    await selectFinisher('FIN-A')
    expect(await screen.findByText('24.50')).toBeInTheDocument()
    await openSharedToy()
    expect(await screen.findByText('Potentially affected')).toBeInTheDocument()
    expect(screen.getAllByText(/Flagged path —/)).toHaveLength(2)
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(expect.arrayContaining([toysAUrl, toysBUrl, detailAUrl, detailBUrl]))
  })

  it('cancels a pending A catalog and ignores its late response after switching to B', async () => {
    const pending = deferredResponse()
    handlers.set(toysAUrl, () => pending.promise)
    renderApp()
    await selectFinisher()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(toysAUrl, expect.anything()))
    const signal = fetchMock.mock.calls.find(([url]) => url === toysAUrl)![1]!.signal!
    await selectFinisher('FIN-B')
    expect(signal.aborted).toBe(true)
    expect(await screen.findByText('31.00')).toBeInTheDocument()
    await act(async () => { pending.resolve(json(catalogA)) })
    expect(screen.queryByText('24.50')).not.toBeInTheDocument()
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
    expect(screen.getByText('No flagged supplier found')).toBeInTheDocument()
  })

  it('cancels a pending A detail and ignores its late flagged paths after switching to B', async () => {
    const pending = deferredResponse()
    handlers.set(detailAUrl, () => pending.promise)
    renderApp()
    await selectFinisher()
    await openSharedToy()
    const signal = fetchMock.mock.calls.find(([url]) => url === detailAUrl)![1]!.signal!
    await selectFinisher('FIN-B')
    expect(signal.aborted).toBe(true)
    await openSharedToy()
    expect(await screen.findByRole('heading', { name: 'Shared train' })).toBeInTheDocument()
    await act(async () => { pending.resolve(json(detailA)) })
    expect(screen.getByText('31.00')).toBeInTheDocument()
    expect(screen.queryByText('Potentially affected')).not.toBeInTheDocument()
    expect(screen.queryByText(/Flagged path —/)).not.toBeInTheDocument()
    expect(screen.getAllByText('Supplier not flagged by this Finisher')).toHaveLength(5)
  })
})
