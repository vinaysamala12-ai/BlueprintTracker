import React, { useEffect, useState } from 'react';
import { getApprovals, getApproval, sendReminder, toggleReminders, getApprovalLogs } from '../../services/api';

const STATUS_OPTS = ['', 'pending', 'in_progress', 'approved', 'rejected'];

export default function ApprovalTracker() {
  const [requests, setRequests] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [msg, setMsg] = useState({ type: '', text: '' });

  useEffect(() => { load(); }, [status, page]);

  async function load() {
    setLoading(true);
    try {
      const res = await getApprovals({ status, search, page, limit: 15 });
      setRequests(res.data.requests || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setLoading(false); }
  }

  async function openDetail(id) {
    setLoadingDetail(true);
    try {
      const [r, l] = await Promise.all([getApproval(id), getApprovalLogs(id)]);
      setSelected(r.data);
      setLogs(l.data || []);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setLoadingDetail(false); }
  }

  async function handleRemind(id) {
    try {
      const res = await sendReminder(id);
      setMsg({ type: 'success', text: `Reminders sent to: ${res.data.sent.join(', ') || 'none pending'}` });
      openDetail(id);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    }
  }

  async function handleToggleReminders(id, enable) {
    try {
      const res = await toggleReminders(id, enable);
      setMsg({ type: 'success', text: res.data.message });
      openDetail(id); // refresh detail panel
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    }
  }

  const statusIcon = { pending: '⏳', approved: '✅', rejected: '❌', changes_made: '✏️' };
  const pages = Math.ceil(total / 15);

  return (
    <>
      <div className="page-header">
        <div><h1>Approval Tracker</h1><p>{total} request{total !== 1 ? 's' : ''}</p></div>
      </div>
      <div className="page-body">
        {msg.text && (
          <div className={`alert alert-${msg.type === 'error' ? 'error' : 'success'}`}>
            {msg.text} <button style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer' }} onClick={() => setMsg({ type: '', text: '' })}>✕</button>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 420px' : '1fr', gap: 24 }}>
          {/* ── List ── */}
          <div>
            {/* Filters */}
            <div className="card card-sm mb-4 flex gap-3 items-center">
              <input
                className="form-input" style={{ maxWidth: 260 }}
                placeholder="Search document name…"
                value={search}
                onChange={e => setSearch(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && load()}
              />
              <select className="form-select" style={{ maxWidth: 160 }} value={status}
                onChange={e => { setStatus(e.target.value); setPage(1); }}>
                <option value="">All Statuses</option>
                {STATUS_OPTS.filter(Boolean).map(s => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
              <button className="btn btn-outline btn-sm" onClick={load}>🔍</button>
            </div>

            <div className="card" style={{ padding: 0 }}>
              {loading
                ? <div className="loading-center"><div className="spinner" /><span>Loading…</span></div>
                : requests.length === 0
                  ? <div className="empty-state"><div className="empty-icon">📭</div><p>No approval requests found</p></div>
                  : requests.map(r => (
                    <div
                      key={r._id}
                      style={{
                        padding: '18px 20px',
                        borderBottom: '1px solid #f1f5f9',
                        cursor: 'pointer',
                        background: selected?._id === r._id ? '#eff6ff' : 'transparent',
                        transition: 'background 0.15s'
                      }}
                      onClick={() => openDetail(r._id)}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span style={{ fontWeight: 600, color: '#1e293b' }}>{r.documentName}</span>
                        <span className={`badge badge-${r.status}`}>{r.status.replace('_', ' ')}</span>
                      </div>
                      <div className="text-muted text-sm mb-2">
                        Submitted by {r.submittedBy} · {new Date(r.createdAt).toLocaleDateString()}
                      </div>

                      {/* Progress */}
                      <div className="flex items-center gap-3">
                        <div className="progress-bar" style={{ flex: 1 }}>
                          <div
                            className={`progress-fill ${r.status === 'approved' ? 'green' : r.status === 'rejected' ? 'red' : 'blue'}`}
                            style={{ width: `${(r.approvedCount / r.requiredApprovals) * 100}%` }}
                          />
                        </div>
                        <span className="text-muted text-sm" style={{ flexShrink: 0 }}>
                          {r.approvedCount}/{r.requiredApprovals}
                        </span>
                      </div>

                      {/* Stakeholder dots */}
                      <div className="flex gap-2 mt-2">
                        {r.approvals?.map(a => (
                          <span key={a._id} title={`${a.name} (${a.email}): ${a.status}`}
                            style={{
                              width: 28, height: 28, borderRadius: '50%',
                              background: a.status === 'approved' ? '#dcfce7' : a.status === 'rejected' ? '#fee2e2' : a.status === 'changes_made' ? '#f5f3ff' : '#fef9c3',
                              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14,
                              border: '2px solid',
                              borderColor: a.status === 'approved' ? '#16a34a' : a.status === 'rejected' ? '#dc2626' : a.status === 'changes_made' ? '#7c3aed' : '#d97706'
                            }}>
                            {statusIcon[a.status]}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))
              }
            </div>

            {pages > 1 && (
              <div className="flex gap-2 mt-4 items-center">
                <button className="btn btn-outline btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Prev</button>
                <span className="text-muted text-sm">Page {page} of {pages}</span>
                <button className="btn btn-outline btn-sm" disabled={page === pages} onClick={() => setPage(p => p + 1)}>Next →</button>
              </div>
            )}
          </div>

          {/* ── Detail panel ── */}
          {selected && (
            <div>
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <div className="section-title">Details</div>
                  <button className="btn btn-outline btn-sm" onClick={() => setSelected(null)}>✕ Close</button>
                </div>

                {loadingDetail
                  ? <div className="loading-center"><div className="spinner" /></div>
                  : <>
                    <div style={{ marginBottom: 16 }}>
                      <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 4 }}>{selected.documentName}</div>
                      {selected.documentWebUrl && (
                        <a href={selected.documentWebUrl} target="_blank" rel="noreferrer" className="text-sm" style={{ color: '#2563eb' }}>
                          View document →
                        </a>
                      )}
                    </div>

                    <table style={{ width: '100%', marginBottom: 16 }}>
                      <tbody>
                        {[
                          ['Status',      <span className={`badge badge-${selected.status}`}>{selected.status.replace('_', ' ')}</span>],
                          ['Submitted by', selected.submittedBy],
                          ['Created',     new Date(selected.createdAt).toLocaleString()],
                          ['Completed',   selected.completedAt ? new Date(selected.completedAt).toLocaleString() : '—'],
                          ['Reminder interval', `${selected.reminderConfig?.intervalHours}h`],
                          ['Max reminders', selected.reminderConfig?.maxReminders],
                        ].map(([k, v]) => (
                          <tr key={k}>
                            <td className="text-muted text-sm" style={{ paddingBottom: 8, paddingRight: 12 }}>{k}</td>
                            <td className="text-sm" style={{ paddingBottom: 8 }}>{v}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>

                    {selected.notes && (
                      <div className="alert alert-info" style={{ marginBottom: 16 }}>
                        <strong>Notes:</strong> {selected.notes}
                      </div>
                    )}

                    <hr className="divider" />
                    <div className="section-title mb-4">Stakeholder Timeline</div>
                    <ul className="timeline">
                      {selected.approvals.map(a => {
                        const amendments = (selected.changeHistory || []).filter(c => c.changedByEmail === a.email);
                        return (
                          <li key={a._id} className="timeline-item">
                            <div className={`timeline-dot ${a.status}`}>{statusIcon[a.status]}</div>
                            <div className="timeline-content">
                              <div className="timeline-name">{a.name}</div>
                              <div className="timeline-email">{a.email}</div>
                              <div className="timeline-meta">
                                {a.status !== 'pending'
                                  ? `${a.status} · ${new Date(a.respondedAt).toLocaleString()}`
                                  : `Pending · ${a.reminderCount} reminder${a.reminderCount !== 1 ? 's' : ''} sent`
                                }
                              </div>
                              {a.comments && (
                                <div className="alert alert-info" style={{ marginTop: 6, padding: '6px 10px', fontSize: 12 }}>
                                  "{a.comments}"
                                </div>
                              )}
                              {amendments.map((c, i) => (
                                <div key={i} className="alert alert-warning" style={{ marginTop: 6, padding: '6px 10px', fontSize: 12 }}>
                                  ✏️ Amended · {new Date(c.changedAt).toLocaleString()}
                                  {c.comments && <> — "{c.comments}"</>}
                                </div>
                              ))}
                            </div>
                          </li>
                        );
                      })}
                    </ul>

                    {['pending', 'in_progress'].includes(selected.status) && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
                        {/* Reminder status banner */}
                        <div style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          padding: '8px 12px', borderRadius: 8,
                          background: selected.remindersEnabled === false ? '#fef2f2' : '#f0fdf4',
                          border: `1px solid ${selected.remindersEnabled === false ? '#fecaca' : '#bbf7d0'}`
                        }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: selected.remindersEnabled === false ? '#dc2626' : '#16a34a' }}>
                            {selected.remindersEnabled === false ? '🔕 Reminders stopped' : '🔔 Reminders active'}
                          </span>
                          {selected.remindersEnabled === false
                            ? <button className="btn btn-sm" style={{ background: '#16a34a', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                                onClick={() => handleToggleReminders(selected._id, true)}>
                                ▶ Resume
                              </button>
                            : <button className="btn btn-sm" style={{ background: '#dc2626', color: '#fff', border: 'none', padding: '4px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 12 }}
                                onClick={() => handleToggleReminders(selected._id, false)}>
                                ⏹ Stop
                              </button>
                          }
                        </div>

                        {/* Manual send — only when reminders are active */}
                        {selected.remindersEnabled !== false && (
                          <button className="btn btn-warning w-full" onClick={() => handleRemind(selected._id)}>
                            🔔 Send Reminders Now
                          </button>
                        )}
                      </div>
                    )}

                    {/* Notification log */}
                    {logs.length > 0 && (
                      <>
                        <hr className="divider" />
                        <div className="section-title mb-4">Notification Log</div>
                        <div style={{ maxHeight: 200, overflowY: 'auto' }}>
                          {logs.map(l => (
                            <div key={l._id} style={{ fontSize: 12, padding: '6px 0', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between' }}>
                              <div>
                                <span className={`badge badge-${l.status}`} style={{ marginRight: 6 }}>{l.type.replace(/_/g, ' ')}</span>
                                <span style={{ color: '#64748b' }}>{l.stakeholderEmail}</span>
                              </div>
                              <div style={{ color: '#94a3b8' }}>
                                {l.emailProvider} · {new Date(l.sentAt).toLocaleDateString()}
                              </div>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </>
                }
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
