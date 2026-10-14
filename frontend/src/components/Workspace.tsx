import { useRef, useState } from 'react'
import type { Finisher } from '../api/catalog'
import { ToysList } from './ToysList'
import { ToyDetails } from './ToyDetails'
import { SuppliersList } from './SuppliersList'
import { SupplierDetails } from './SupplierDetails'

type Tab = 'toys' | 'suppliers'

export function Workspace({ finisher }: { finisher: Finisher }) {
  const [tab, setTab] = useState<Tab>('toys')
  const [toyId, setToyId] = useState<string | null>(null)
  const [supplierId, setSupplierId] = useState<string | null>(null)
  const toysTab = useRef<HTMLButtonElement>(null)
  const suppliersTab = useRef<HTMLButtonElement>(null)

  function selectTab(next: Tab) {
    setTab(next)
    setToyId(null)
    setSupplierId(null)
  }

  return (
    <>
      <p className="scope-notice">
        Flags apply only to {finisher.finisher_name}. “No flagged supplier found” means this
        Finisher has not flagged any supplier on the listed paths — not that the toy or its
        suppliers are verified safe or free of child labor.
      </p>
      <div
        className="workspace-tabs"
        role="tablist"
        aria-label="Workspace"
        onKeyDown={(event) => {
          let next: Tab
          if (event.key === 'Home') next = 'toys'
          else if (event.key === 'End') next = 'suppliers'
          else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            next = tab === 'toys' ? 'suppliers' : 'toys'
          } else return
          event.preventDefault()
          selectTab(next)
          const nextTab = next === 'toys' ? toysTab : suppliersTab
          nextTab.current?.focus()
        }}
      >
        <button
          ref={toysTab}
          id="toys-tab"
          role="tab"
          aria-controls="workspace-panel"
          aria-selected={tab === 'toys'}
          tabIndex={tab === 'toys' ? 0 : -1}
          onClick={() => selectTab('toys')}
        >Toys</button>
        <button
          ref={suppliersTab}
          id="suppliers-tab"
          role="tab"
          aria-controls="workspace-panel"
          aria-selected={tab === 'suppliers'}
          tabIndex={tab === 'suppliers' ? 0 : -1}
          onClick={() => selectTab('suppliers')}
        >Suppliers</button>
      </div>
      <div id="workspace-panel" className="workspace-panel" role="tabpanel" aria-labelledby={`${tab}-tab`}>
        {tab === 'suppliers' ? (
          supplierId === null ? (
            <SuppliersList finisherId={finisher.finisher_id} onSelect={setSupplierId} />
          ) : (
            <SupplierDetails
              key={supplierId}
              finisherId={finisher.finisher_id}
              supplierId={supplierId}
              onBack={() => {
                setSupplierId(null)
                suppliersTab.current?.focus()
              }}
            />
          )
        ) : toyId === null ? (
          <ToysList finisherId={finisher.finisher_id} onSelect={setToyId} />
        ) : (
          <ToyDetails
            finisherId={finisher.finisher_id}
            toyId={toyId}
            onBack={() => {
              setToyId(null)
              toysTab.current?.focus()
            }}
          />
        )}
      </div>
    </>
  )
}
