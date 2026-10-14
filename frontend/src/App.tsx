import { useState } from 'react'
import type { Finisher } from './api/catalog'
import { FinisherPicker } from './components/FinisherPicker'
import { Workspace } from './components/Workspace'
import './App.css'

function App() {
  const [finisher, setFinisher] = useState<Finisher | null>(null)

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">Supply-chain traceability</p>
          <h1>FairToy</h1>
          {finisher && (
            <p className="selected-finisher">
              Selected Finisher: <strong>{finisher.finisher_name}</strong>{' '}
              <span className="record-id">{finisher.finisher_id} · {finisher.hq_country}</span>
            </p>
          )}
        </div>
        <FinisherPicker selected={finisher} onSelect={setFinisher} />
      </header>
      {finisher && <Workspace key={finisher.finisher_id} finisher={finisher} />}
    </main>
  )
}

export default App
