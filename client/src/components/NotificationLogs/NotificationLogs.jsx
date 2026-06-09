import React, { useEffect, useState } from 'react';
import { getAllLogs } from '../../services/api';

const TYPE_LABELS = {
  approval_request: '📨 Initial Request',
  reminder:         '🔔 Reminder',
  approved_notify:  '✅ Approved Notify',
  rejected_notify:  '❌ Rejected Notify',
  all_approved:     '🎉 All Approved',
  test:             '🧪 Test'
};

export default function NotificationLogs() {
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, [page]);

  async function load() {
    setLoading(true);
    try {
      const res = await getAllLogs({ page, limit: 50 });
      setLogs(res.data.logs || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      setError(e.message);
    } finally { setLoading(false); }
  }

  const pages = Math.ceil(total / 50);

  return (
    <>
      <div className="page-header">
        <div><h1>Notification Logs</h1><p>{total} email{total !== 1 ? 's' : ''} sent</p></div>
      </div>
      <div className="page-body">
        {error && <div className="alert alert-error">{error}</div>}
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            {loading
              ? <div className="loading-center"><div className="spinner" /><span>Loading…</span></div>
              : logs.length === 0
                ? <div className="empty-state"><div className="empty-icon">📭</div><p>No notifications sent yet</p></div>
                : (
                  <table>
                    <thead>
                      <tr>
                        <th>Type</th>
                        <th>Document</th>
                        <th>Recipient</th>
                        <th>Via</th>
                        <th>Status</th>
                        <th>Sent At</th>
                        <th>Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {logs.map(l => (
                        <tr key={l._id}>
                          <td>{TYPE_LABELS[l.type] || l.type}</td>
                          <td>
                            <div style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {l.documentName || '—'}
                            </div>
                          </td>
                          <td>
                            <div>{l.stakeholderName}</div>
                            <div className="text-muted">{l.stakeholderEmail}</div>
                          </td>
                          <td>
                            <span className="badge badge-in_review">🏢 MS365</span>
                          </td>
                          <td><span className={`badge badge-${l.status}`}>{l.status}</span></td>
                          <td className="text-muted">{new Date(l.sentAt).toLocaleString()}</td>
                          <td className="text-muted" style={{ color: '#dc2626', fontSize: 12 }}>
                            {l.errorMessage || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )
            }
          </div>
        </div>

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
