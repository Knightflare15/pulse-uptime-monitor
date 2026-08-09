import React, { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const API = '/api'

function normaliseUrl(value) {
  const trimmed = value.trim()
  return /^https?:\/\//i.test(trimmed) ? trimmed : 'http://' + trimmed
}

function toErrorMessage(detail, fallback) {
  if (Array.isArray(detail)) return detail.map(item => item.msg || fallback).join('. ')
  return typeof detail === 'string' ? detail : fallback
}

function elapsed(iso) {
  if (!iso) return 'Never checked'
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  return `${Math.floor(seconds / 60)}m ago`
}

function Badge({ status }) {
  return <span className={`badge ${status}`}><i />{status}</span>
}

function App() {
  const [monitors, setMonitors] = React.useState([])
  const [url, setUrl] = React.useState('')
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(true)
  const [submitting, setSubmitting] = React.useState(false)
  const [checking, setChecking] = React.useState(null)

  const refresh = React.useCallback(async () => {
    try {
      const response = await fetch(`${API}/monitors`)
      if (!response.ok) throw new Error('Could not load monitors')
      const data = await response.json()
      setMonitors(data.monitors)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  async function addMonitor(event) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const response = await fetch(`${API}/monitors`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: normaliseUrl(url) })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(toErrorMessage(data.detail, 'Could not add monitor'))
      setUrl('')
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function checkNow(id) {
    setChecking(id)
    try {
      const response = await fetch(`${API}/monitors/${id}/check`, { method: 'POST' })
      if (!response.ok) throw new Error('Check failed')
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setChecking(null)
    }
  }

  async function remove(id) {
    if (!window.confirm('Stop monitoring this URL?')) return
    const response = await fetch(`${API}/monitors/${id}`, { method: 'DELETE' })
    if (!response.ok) setError('Could not remove monitor')
    await refresh()
  }

  const counts = monitors.reduce((totals, item) => ({ ...totals, [item.status]: totals[item.status] + 1 }), { up: 0, down: 0, pending: 0 })

  return <main>
    <section className="hero">
      <div><p className="eyebrow">SYSTEM STATUS</p><h1>Pulse</h1><p className="subtitle">A lightweight heartbeat for the services you depend on.</p></div>
      <div className="updated">Refreshes every 5 seconds<br /><span>Checks run every minute</span></div>
    </section>

    <section className="summary" aria-label="Status summary">
      <div><span>Operational</span><strong>{counts.up}</strong></div>
      <div><span>Down</span><strong>{counts.down}</strong></div>
      <div><span>Pending</span><strong>{counts.pending}</strong></div>
    </section>

    <section className="panel add-panel">
      <div><h2>Monitor a URL</h2><p>HTTP and HTTPS endpoints are checked every minute.</p></div>
      <form onSubmit={addMonitor}>
        <input aria-label="URL to monitor" type="url" value={url} onChange={event => setUrl(event.target.value)} placeholder="https://example.com" required />
        <button disabled={submitting}>{submitting ? 'Checking...' : 'Add monitor'}</button>
      </form>
    </section>

    {error && <p className="error" role="alert">{error}</p>}

    <section className="panel monitors">
      <div className="section-heading"><div><h2>Monitors</h2><p>{monitors.length ? `${monitors.length} endpoint${monitors.length === 1 ? '' : 's'} tracked` : 'No endpoints yet'}</p></div><button className="quiet" onClick={refresh}>Refresh</button></div>
      {loading ? <p className="empty">Loading your monitors...</p> : monitors.length === 0 ? <p className="empty">Add your first endpoint above. It will be checked immediately.</p> : <div className="table-wrap"><table><thead><tr><th>Endpoint</th><th>Status</th><th>Response</th><th>Last check</th><th aria-label="Actions" /></tr></thead><tbody>{monitors.map(monitor => <tr key={monitor.id}><td><a href={monitor.url} target="_blank" rel="noreferrer">{monitor.url}</a>{monitor.latest_check?.error && <small title={monitor.latest_check.error}>{monitor.latest_check.error}</small>}</td><td><Badge status={monitor.status} /></td><td>{monitor.latest_check?.response_time_ms != null ? `${Math.round(monitor.latest_check.response_time_ms)} ms` : '--'}</td><td>{elapsed(monitor.latest_check?.checked_at)}</td><td className="actions"><button className="quiet" onClick={() => checkNow(monitor.id)} disabled={checking === monitor.id}>{checking === monitor.id ? 'Checking...' : 'Check now'}</button><button className="icon" aria-label={`Remove ${monitor.url}`} onClick={() => remove(monitor.id)}>x</button></td></tr>)}</tbody></table></div>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
