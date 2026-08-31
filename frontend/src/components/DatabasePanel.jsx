import { useEffect, useState } from 'react'
import { api, humanDate, humanSize } from '../api'

// One-click maintenance actions. Anything destructive asks first, and nothing
// here ever touches the actual image files on disk.
const ACTIONS = [
  {
    key: 'rescanAll',
    label: 'Scan all folders for new images',
    help: 'Adds pictures you saved since the last scan. Skips anything unchanged.',
    run: () => api.rescanAll(),
  },
  {
    key: 'prune',
    label: 'Remove entries for deleted files',
    help: 'Cleans up index rows whose picture was moved or deleted.',
    run: () => api.prune(),
    describe: (r) => `Removed ${r.pruned} stale entr${r.pruned === 1 ? 'y' : 'ies'}.`,
  },
  {
    key: 'vacuum',
    label: 'Optimise the database',
    help: 'Reclaims disk space and keeps searches fast.',
    run: () => api.vacuum(),
    describe: () => 'Database optimised.',
  },
  {
    key: 'reindex',
    label: 'Rebuild every vector from scratch',
    help: 'Slow. Only needed if the index looks wrong or the model changed.',
    confirm: 'Re-process every image in every folder? This can take a while.',
    run: () => api.reindex(),
  },
  {
    key: 'clear',
    label: 'Delete all indexed data',
    help: 'Empties the index. Your picture files are left alone.',
    confirm: 'Delete every stored vector?\n\nYour image files are NOT deleted.',
    danger: true,
    run: () => api.clear(true),
    describe: (r) => `Cleared ${r.removed} entries.`,
  },
]

export default function DatabasePanel({ status, job, refresh, onJobStarted }) {
  const [stats, setStats] = useState(null)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [running, setRunning] = useState('')

  const loadStats = async () => {
    try {
      setStats(await api.stats())
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { loadStats() }, [status.images])

  const perform = async (action) => {
    if (action.confirm && !confirm(action.confirm)) return
    setRunning(action.key); setMessage(''); setError('')
    try {
      const result = await action.run()
      if (result?.id) {
        onJobStarted(result)
        setMessage('Job started - progress is shown at the top.')
      } else {
        setMessage(action.describe ? action.describe(result) : 'Done.')
      }
      await Promise.all([loadStats(), refresh()])
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning('')
    }
  }

  return (
    <section>
      <div className="panel">
        <h2>What is stored</h2>
        <div className="stat-row">
          <Stat label="Images indexed" value={status.images.toLocaleString()} />
          <Stat label="Folders" value={status.folders} />
          <Stat label="Database size" value={stats?.database_size ?? '-'} />
          <Stat label="Pictures on disk" value={stats ? humanSize(stats.indexed_bytes) : '-'} />
          <Stat label="Vector size" value={`${status.model.dimensions} numbers`} />
        </div>
        {stats?.newest && (
          <p className="muted small">
            Oldest entry {humanDate(stats.oldest)} · newest {humanDate(stats.newest)}
          </p>
        )}
      </div>

      <div className="panel">
        <h2>One-click actions</h2>
        <div className="actions">
          {ACTIONS.map((action) => (
            <div key={action.key} className={`action ${action.danger ? 'danger' : ''}`}>
              <div>
                <strong>{action.label}</strong>
                <p className="muted small">{action.help}</p>
              </div>
              <button
                className={`btn ${action.danger ? 'danger' : ''}`}
                disabled={Boolean(job) || Boolean(running)}
                onClick={() => perform(action)}
              >
                {running === action.key ? 'Working…' : 'Run'}
              </button>
            </div>
          ))}
        </div>
        {message && <p className="ok">{message}</p>}
        {error && <p className="error">{error}</p>}
      </div>

      {stats?.per_folder?.length > 0 && (
        <div className="panel">
          <h2>Images per folder</h2>
          <table className="table">
            <thead><tr><th>Folder</th><th className="right">Images</th></tr></thead>
            <tbody>
              {stats.per_folder.map((row) => (
                <tr key={row.path}>
                  <td className="mono truncate">{row.path}</td>
                  <td className="right">{row.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <span className="stat-value">{value}</span>
      <span className="muted small">{label}</span>
    </div>
  )
}
