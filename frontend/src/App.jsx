import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import SearchPanel from './components/SearchPanel'
import FoldersPanel from './components/FoldersPanel'
import DatabasePanel from './components/DatabasePanel'
import JobProgress from './components/JobProgress'

const TABS = [
  { key: 'search', label: 'Search' },
  { key: 'folders', label: 'Folders' },
  { key: 'database', label: 'Database' },
]

export default function App() {
  const [tab, setTab] = useState('search')
  const [status, setStatus] = useState(null)
  const [folders, setFolders] = useState([])
  const [job, setJob] = useState(null)
  const [offline, setOffline] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const [next, folderList] = await Promise.all([api.status(), api.folders()])
      setStatus(next)
      setFolders(folderList)
      setJob(next.active_job)
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  // Poll fast while a job runs, slowly when idle.
  useEffect(() => {
    const interval = setInterval(refresh, job ? 1000 : 8000)
    return () => clearInterval(interval)
  }, [job, refresh])

  if (offline || !status) {
    return (
      <div className="boot">
        <h1>Semantic Image Finder</h1>
        <p className="muted">
          {offline ? 'Waiting for the backend on port 8000…' : 'Starting up…'}
        </p>
        <p className="muted small">
          If this does not clear, check the Terminal window where you ran <code>./start.sh</code>.
        </p>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">◐</span>
          <div>
            <h1>Semantic Image Finder</h1>
            <p className="muted small">
              {status.images.toLocaleString()} images across {status.folders} folder
              {status.folders === 1 ? '' : 's'}
            </p>
          </div>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'tab on' : 'tab'}
                    onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {!status.postgres_connected && (
        <div className="banner error">
          <strong>PostgreSQL is not running.</strong> Open Terminal and run{' '}
          <code>brew services start postgresql@18</code>. Details: {status.postgres_error}
        </div>
      )}

      <main>
        <JobProgress job={job} />

        {tab === 'search' && <SearchPanel folders={folders} />}
        {tab === 'folders' && (
          <FoldersPanel folders={folders} job={job} refresh={refresh} onJobStarted={setJob} />
        )}
        {tab === 'database' && (
          <DatabasePanel status={status} job={job} refresh={refresh} onJobStarted={setJob} />
        )}
      </main>

      <footer className="footer muted small">
        {status.model.model} on {status.model.device} · Postgres {status.database} @ {status.host}
      </footer>
    </div>
  )
}
