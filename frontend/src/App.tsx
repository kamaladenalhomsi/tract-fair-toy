import { useQuery } from '@tanstack/react-query'
import './App.css'

type HealthResponse = {
  status: 'ok'
  database: 'ok'
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('/api/health')

  if (!response.ok) {
    throw new Error('Health check failed')
  }

  return response.json() as Promise<HealthResponse>
}

function App() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    retry: false,
  })

  return (
    <main className="app-shell">
      <header>
        <p className="eyebrow">Supply-chain traceability</p>
        <h1>FairToy</h1>
      </header>

      <section className="status-card" aria-live="polite">
        <h2>Local system status</h2>
        {health.isPending && <p>Checking backend and database…</p>}
        {health.isError && (
          <p className="status-error">Backend or database unavailable.</p>
        )}
        {health.data && (
          <p className="status-ok">Backend and database connected.</p>
        )}
      </section>
    </main>
  )
}

export default App
