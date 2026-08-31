import { useRef, useState } from 'react'
import { api } from '../api'
import ResultsGrid from './ResultsGrid'

const TOP_K_CHOICES = [3, 5, 10, 20, 50, 100]

export default function SearchPanel({ folders }) {
  const [mode, setMode] = useState('image')      // 'image' | 'text'
  const [topK, setTopK] = useState(10)
  const [folderId, setFolderId] = useState('')
  const [text, setText] = useState('')
  const [dropped, setDropped] = useState(null)
  const [results, setResults] = useState(null)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileInput = useRef(null)

  const run = async (fn, describe) => {
    setBusy(true); setError(''); setResults(null)
    try {
      const data = await fn()
      setResults(data.results)
      setLabel(describe(data))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const runImage = (file) => {
    if (!file) return
    setDropped({ name: file.name, url: URL.createObjectURL(file) })
    run(() => api.searchByImage(file, topK, folderId),
        (d) => `Images most like “${d.query}”`)
  }

  const runText = () => {
    if (!text.trim()) return
    setDropped(null)
    run(() => api.searchByText(text.trim(), topK, folderId),
        (d) => `Images matching “${d.query}”`)
  }

  const findSimilar = (item) => {
    setDropped(null)
    run(() => api.searchSimilar(item.id, topK, folderId),
        () => `Images most like “${item.file_name}”`)
  }

  return (
    <section>
      <div className="panel">
        <div className="tabs">
          <button className={mode === 'image' ? 'tab on' : 'tab'} onClick={() => setMode('image')}>
            Search by image
          </button>
          <button className={mode === 'text' ? 'tab on' : 'tab'} onClick={() => setMode('text')}>
            Search by words
          </button>
        </div>

        {mode === 'image' ? (
          <div
            className="dropzone"
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); runImage(e.dataTransfer.files[0]) }}
          >
            {dropped ? (
              <img className="dropped" src={dropped.url} alt={dropped.name} />
            ) : (
              <>
                <div className="drop-ico">🖼️</div>
                <p><strong>Drop an image here</strong> or click to choose one</p>
                <p className="muted small">We find the pictures in your folders that look most like it.</p>
              </>
            )}
            <input
              ref={fileInput} type="file" accept="image/*" hidden
              onChange={(e) => runImage(e.target.files[0])}
            />
          </div>
        ) : (
          <div className="path-row">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runText()}
              placeholder="a dog on a beach at sunset"
            />
            <button className="btn primary" onClick={runText} disabled={busy}>Search</button>
          </div>
        )}

        <div className="controls">
          <label>
            Show top
            <select value={topK} onChange={(e) => {
              const next = Number(e.target.value)
              setTopK(next)
            }}>
              {TOP_K_CHOICES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label>
            Look in
            <select value={folderId} onChange={(e) => setFolderId(e.target.value)}>
              <option value="">All folders</option>
              {folders.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.path.split('/').pop()} ({f.image_count})
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {busy && <p className="muted pad">Searching…</p>}
      {error && <p className="error">{error}</p>}
      {label && !busy && <h3 className="results-title">{label}</h3>}
      {!busy && <ResultsGrid results={results} onFindSimilar={findSimilar} />}
    </section>
  )
}
