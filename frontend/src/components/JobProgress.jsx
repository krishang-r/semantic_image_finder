import { api } from '../api'

export default function JobProgress({ job }) {
  if (!job) return null
  const running = ['queued', 'scanning', 'running'].includes(job.status)

  return (
    <div className={`job job-${job.status}`}>
      <div className="job-head">
        <strong>
          {running ? 'Indexing' : job.status === 'done' ? 'Finished' : job.status}
        </strong>
        <span className="mono truncate">{job.folder}</span>
        {running && (
          <button className="btn tiny ghost" onClick={() => api.cancelJob(job.id)}>Stop</button>
        )}
      </div>

      <div className="bar"><div className="bar-fill" style={{ width: `${job.percent}%` }} /></div>

      <div className="job-meta">
        <span>{job.processed} / {job.total || '?'} files</span>
        {job.current && <span className="truncate">{job.current}</span>}
        <span>{job.elapsed}s</span>
      </div>
      {job.message && <p className="muted small">{job.message}</p>}
    </div>
  )
}
