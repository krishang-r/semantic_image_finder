import { useEffect, useState } from 'react'
import { api } from '../api'

// Browsers refuse to reveal a real directory path from a file input, so the
// backend lists directories for us and the user clicks their way to one.
export default function FolderBrowser({ onPick, onClose }) {
  const [state, setState] = useState({ path: '', parent: null, entries: [] })
  const [typed, setTyped] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const go = async (path) => {
    setLoading(true)
    setError('')
    try {
      const data = await api.browse(path)
      setState(data)
      setTyped(data.path)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { go('') }, [])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>Choose a folder</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="path-row">
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && go(typed)}
            placeholder="/Users/you/Pictures"
            spellCheck={false}
          />
          <button className="btn ghost" onClick={() => go(typed)}>Go</button>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="browser-list">
          {state.parent && (
            <button className="row-btn" onClick={() => go(state.parent)}>
              <span className="ico">↰</span> .. (up one level)
            </button>
          )}
          {loading && <p className="muted pad">Loading…</p>}
          {!loading && state.entries.length === 0 && (
            <p className="muted pad">No sub-folders here. You can still select this folder.</p>
          )}
          {state.entries.map((entry) => (
            <button key={entry.path} className="row-btn" onClick={() => go(entry.path)}>
              <span className="ico">📁</span> {entry.name}
            </button>
          ))}
        </div>

        <footer className="modal-foot">
          <span className="muted mono truncate">{state.path}</span>
          <button className="btn primary" disabled={!state.path}
                  onClick={() => onPick(state.path)}>
            Index this folder
          </button>
        </footer>
      </div>
    </div>
  )
}
