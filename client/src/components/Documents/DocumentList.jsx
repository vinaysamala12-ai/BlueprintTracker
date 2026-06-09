import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDocuments, deleteDocument } from '../../services/api';

const STATUS_OPTS = ['', 'pending', 'in_review', 'approved', 'rejected'];

export default function DocumentList() {
  const [docs, setDocs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [msg, setMsg] = useState({ type: '', text: '' });

  useEffect(() => { load(); }, [status, page]);

  async function load() {
    setLoading(true);
    try {
      const res = await getDocuments({ status, search, page, limit: 15 });
      setDocs(res.data.documents);
      setTotal(res.data.total);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id, name) {
    if (!window.confirm(`Delete "${name}"? This will also remove its approval request.`)) return;
    try {
      await deleteDocument(id);
      setMsg({ type: 'success', text: 'Document deleted.' });
      load();
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    }
  }

  function fmt(bytes) {
    if (!bytes) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  const pages = Math.ceil(total / 15);

  return (
    <>
      <div className="page-header">
        <div><h1>Documents</h1><p>{total} document{total !== 1 ? 's' : ''}</p></div>
        <Link to="/submit" className="btn btn-primary">⬆️ Submit New</Link>
      </div>
      <div className="page-body">
        {msg.text && (
          <div className={`alert alert-${msg.type === 'error' ? 'error' : 'success'}`}>
            {msg.text}
          </div>
        )}

        {/* Filters */}
        <div className="card card-sm mb-4 flex gap-3 items-center">
          <input
            className="form-input" style={{ maxWidth: 280 }}
            placeholder="Search by name…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && load()}
          />
          <select className="form-select" style={{ maxWidth: 160 }} value={status} onChange={e => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All Statuses</option>
            {STATUS_OPTS.filter(Boolean).map(s => (
              <option key={s} value={s}>{s.replace('_', ' ')}</option>
            ))}
          </select>
          <button className="btn btn-outline btn-sm" onClick={load}>🔍 Search</button>
        </div>

        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            {loading
              ? <div className="loading-center"><div className="spinner" /><span>Loading…</span></div>
              : docs.length === 0
                ? <div className="empty-state"><div className="empty-icon">📭</div><p>No documents found</p></div>
                : (
                  <table>
                    <thead>
                      <tr>
                        <th>Document</th>
                        <th>Storage</th>
                        <th>Size</th>
                        <th>Submitted By</th>
                        <th>Status</th>
                        <th>Submitted</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {docs.map(d => (
                        <tr key={d._id}>
                          <td>
                            <div style={{ fontWeight: 600 }}>{d.name}</div>
                            <div className="text-muted">{d.path}</div>
                          </td>
                          <td>
                            <span className={`badge ${d.storageType === 'sharepoint' ? 'badge-approved' : 'badge-in_review'}`}>
                              {d.storageType === 'sharepoint' ? '🏢 SharePoint' : '☁️ OneDrive'}
                            </span>
                          </td>
                          <td>{fmt(d.fileSize)}</td>
                          <td>
                            <div>{d.submittedBy}</div>
                            <div className="text-muted">{d.submittedByEmail}</div>
                          </td>
                          <td><span className={`badge badge-${d.status}`}>{d.status.replace('_', ' ')}</span></td>
                          <td className="text-muted">{new Date(d.createdAt).toLocaleDateString()}</td>
                          <td>
                            <div className="flex gap-2">
                              {d.webUrl && (
                                <a href={d.webUrl} target="_blank" rel="noreferrer" className="btn btn-outline btn-sm">View</a>
                              )}
                              {d.approvalRequestId && (
                                <Link to={`/approvals`} className="btn btn-outline btn-sm">Track</Link>
                              )}
                              <button className="btn btn-danger btn-sm" onClick={() => handleDelete(d._id, d.name)}>🗑</button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
            }
          </div>
        </div>

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex gap-2 mt-4 items-center">
            <button className="btn btn-outline btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
            <span className="text-muted text-sm">Page {page} of {pages}</span>
            <button className="btn btn-outline btn-sm" disabled={page === pages} onClick={() => setPage(p => p + 1)}>Next →</button>
          </div>
        )}
      </div>
    </>
  );
}
