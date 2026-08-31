import { useState } from 'react'
import { api, humanDate } from '../api'
import FolderBrowser from './FolderBrowser'

export default function FoldersPanel({ folders, job, refresh, onJobStarted }) {
  const [picking, setPicking] = useState(false)
  const [error, setError] = useState('')
  const busy = Boolean(job)

  const guard = async (fn) => {
    setError('')
    try {
      const result = await fn()
      if (result?.id) onJobStarted(result)
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>Folders being watched</h2>
            <p className="muted small">
              Every sub-folder inside these is included, however deeply nested.
            </p>
          </div>
          <button className="btn primary" disabled={busy} onClick={() => setPicking(true)}>
            + Add folder
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        {folders.length === 0 ? (
          <p className="muted pad">
            Nothing indexed yet. Click <strong>Add folder</strong> to point it at your pictures.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Folder</th><th>Images</th><th>Added</th><th>Last scan</th><th /></tr>
            </thead>
            <tbody>
              {folders.map((f) => (
                <tr key={f.id}>
                  <td>
                    <span className="mono truncate" title={f.path}>{f.path}</span>
                    {!f.exists && <span className="pill warn">missing on disk</span>}
                  </td>
                  <td>{f.image_count}</td>
                  <td className="muted small">{humanDate(f.date_added)}</td>
                  <td className="muted small">{humanDate(f.last_scanned_at)}</td>
                  <td className="right nowrap">
                    <button className="btn tiny" disabled={busy || !f.exists}
                            onClick={() => guard(() => api.rescanFolder(f.id, false))}>
                      Scan for new
                    </button>
                    <button className="btn tiny ghost" disabled={busy || !f.exists}
                            onClick={() => guard(() => api.rescanFolder(f.id, true))}>
                      Rebuild
                    </button>
                    <button className="btn tiny danger" disabled={busy}
                            onClick={() => {
                              if (confirm(`Remove ${f.path} from the index?\n\nYour picture files are NOT deleted.`)) {
                                guard(() => api.removeFolder(f.id))
                              }
                            }}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {picking && (
        <FolderBrowser
          onClose={() => setPicking(false)}
          onPick={(path) => { setPicking(false); guard(() => api.addFolder(path)) }}
        />
      )}
    </section>
  )
}
