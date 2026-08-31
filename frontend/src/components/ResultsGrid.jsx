import { useState } from 'react'
import { api, fileUrl, humanSize, thumbUrl } from '../api'

export default function ResultsGrid({ results, onFindSimilar }) {
  const [preview, setPreview] = useState(null)

  if (!results) return null
  if (results.length === 0) {
    return <p className="muted pad">No matches. Try adding a folder, or widen your search.</p>
  }

  return (
    <>
      <div className="grid">
        {results.map((item) => (
          <figure key={item.id} className="card">
            <button className="thumb" onClick={() => setPreview(item)}>
              <img src={thumbUrl(item.path)} alt={item.file_name} loading="lazy" />
              {item.similarity !== undefined && (
                <span className="score">{(item.similarity * 100).toFixed(1)}%</span>
              )}
            </button>
            <figcaption>
              <span className="name truncate" title={item.path}>{item.file_name}</span>
              <span className="muted small">
                {item.width}×{item.height} · {humanSize(item.file_size)}
              </span>
              <div className="card-actions">
                <button className="btn tiny" onClick={() => onFindSimilar(item)}>
                  More like this
                </button>
                <button className="btn tiny ghost" onClick={() => api.reveal(item.path)}>
                  Finder
                </button>
              </div>
            </figcaption>
          </figure>
        ))}
      </div>

      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <div className="lightbox" onClick={(e) => e.stopPropagation()}>
            <img src={fileUrl(preview.path)} alt={preview.file_name} />
            <div className="lightbox-bar">
              <span className="mono truncate">{preview.path}</span>
              <button className="btn tiny ghost" onClick={() => api.reveal(preview.path)}>
                Show in Finder
              </button>
              <button className="icon-btn" onClick={() => setPreview(null)}>✕</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
