// Thin wrapper around the backend. Every call goes through Vite's /api proxy.

async function request(path, options = {}) {
  const res = await fetch(path, options)
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch {
      /* response was not JSON */
    }
    throw new Error(detail)
  }
  return res.status === 204 ? null : res.json()
}

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  status: () => request('/api/status'),
  browse: (path = '') => request(`/api/browse?path=${encodeURIComponent(path)}`),

  folders: () => request('/api/folders'),
  addFolder: (path) => request('/api/folders', json({ path })),
  rescanFolder: (id, force = false) =>
    request(`/api/folders/${id}/rescan?force=${force}`, { method: 'POST' }),
  removeFolder: (id) => request(`/api/folders/${id}`, { method: 'DELETE' }),

  job: (id) => request(`/api/jobs/${id}`),
  cancelJob: (id) => request(`/api/jobs/${id}/cancel`, { method: 'POST' }),

  searchByText: (query, topK, folderId) =>
    request('/api/search/text', json({ query, top_k: topK, folder_id: folderId || null })),
  searchByImage: (file, topK, folderId) => {
    const form = new FormData()
    form.append('file', file)
    const scope = folderId ? `&folder_id=${folderId}` : ''
    return request(`/api/search/image?top_k=${topK}${scope}`, { method: 'POST', body: form })
  },
  searchSimilar: (imageId, topK, folderId) =>
    request(`/api/search/similar/${imageId}`, json({ top_k: topK, folder_id: folderId || null })),

  recent: (limit = 60) => request(`/api/images?limit=${limit}`),
  reveal: (path) => request('/api/reveal', json({ path })),

  stats: () => request('/api/admin/stats'),
  prune: () => request('/api/admin/prune', { method: 'POST' }),
  vacuum: () => request('/api/admin/vacuum', { method: 'POST' }),
  reindex: () => request('/api/admin/reindex', { method: 'POST' }),
  rescanAll: () => request('/api/admin/rescan-all', { method: 'POST' }),
  clear: (keepFolders) =>
    request('/api/admin/clear', json({ confirm: 'DELETE', keep_folders: keepFolders })),
}

export const thumbUrl = (path, size = 320) =>
  `/api/thumb?size=${size}&path=${encodeURIComponent(path)}`
export const fileUrl = (path) => `/api/file?path=${encodeURIComponent(path)}`

export function humanSize(bytes) {
  if (!bytes) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / 1024 ** i).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function humanDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
