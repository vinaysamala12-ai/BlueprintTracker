import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getDocumentStats, getApprovalStats, getSchedulerStatus, runSchedulerNow, getApprovals } from '../../services/api';

export default function Dashboard() {
  const isAdmin = localStorage.getItem('auth_role') === 'admin';
  const [docStats, setDocStats] = useState(null);
  const [aprStats, setAprStats] = useState(null);
  const [scheduler, setScheduler] = useState(null);
  const [recent, setRecent] = useState([]);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const [d, a, s, r] = await Promise.all([
        getDocumentStats(),
        getApprovalStats(),
        getSchedulerStatus(),
        getApprovals({ limit: 5 })
      ]);
      setDocStats(d.data);
      setAprStats(a.data);
      setScheduler(s.data);
      setRecent(r.data.requests || []);
    } catch (e) {
      console.error(e);
    }
  }

  async function handleRunNow() {
    setRunning(true);
    setMsg('');
    try {
      await runSchedulerNow();
      setMsg('Scheduler ran — reminders processed.');
      load();
    } catch (e) {
      setMsg(e.message);
    } finally {
      setRunning(false);
    }
  }

  const statusColor = { pending: 'yellow', in_review: 'blue', in_progress: 'blue', approved: 'green', rejected: 'red' };

  return (
    <>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>Overview of the document approval workflow</p>
        </div>
        <Link to="/submit" className="btn btn-primary">⬆️ Submit Document</Link>
      </div>

      <div className="page-body">
        {msg && <div className={`alert ${msg.includes('ran') ? 'alert-success' : 'alert-error'}`}>{msg}</div>}

        {/* ── Document Stats ── */}
        <div className="section-header">
          <div>
            <div className="section-title">Documents</div>
            <div className="section-sub">Across all statuses</div>
          </div>
        </div>
        <div className="stats-grid">
          {[
            { label: 'Total Documents', value: docStats?.total ?? '–', icon: '📄', cls: 'blue'   },
            { label: 'Pending',         value: docStats?.pending ?? '–', icon: '⏳', cls: 'yellow' },
            { label: 'In Review',       value: docStats?.in_review ?? '–', icon: '🔍', cls: 'orange' },
            { label: 'Approved',        value: docStats?.approved ?? '–', icon: '✅', cls: 'green'  },
            { label: 'Rejected',        value: docStats?.rejected ?? '–', icon: '❌', cls: 'red'    },
          ].map(s => (
            <div key={s.label} className="stat-card">
              <div className={`stat-icon ${s.cls}`}>{s.icon}</div>
              <div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* ── Approval Stats ── */}
        <div className="section-header mt-6">
          <div>
            <div className="section-title">Approvals</div>
            <div className="section-sub">Stakeholder decisions</div>
          </div>
        </div>
        <div className="stats-grid">
          {[
            { label: 'Total Requests', value: aprStats?.total ?? '–', icon: '📋', cls: 'blue'   },
            { label: 'In Progress',    value: aprStats?.in_progress ?? '–', icon: '⚡', cls: 'orange' },
            { label: 'Approved',       value: aprStats?.approved ?? '–', icon: '✅', cls: 'green'  },
            { label: 'Rejected',       value: aprStats?.rejected ?? '–', icon: '❌', cls: 'red'    },
            { label: 'Reminders Sent', value: aprStats?.reminderCount ?? '–', icon: '🔔', cls: 'purple' },
          ].map(s => (
            <div key={s.label} className="stat-card">
              <div className={`stat-icon ${s.cls}`}>{s.icon}</div>
              <div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            </div>
          ))}
        </div>

        <div className={`mt-6 ${isAdmin ? 'grid-2' : ''}`}>
          {/* ── Scheduler card (admin only) ── */}
          {isAdmin && (
            <div className="card">
              <div className="section-header mb-4">
                <div className="section-title">⏰ Scheduler</div>
                <button className="btn btn-outline btn-sm" onClick={handleRunNow} disabled={running}>
                  {running ? 'Running…' : '▶ Run Now'}
                </button>
              </div>
              {scheduler ? (
                <div>
                  <div className="flex items-center gap-2 mb-4">
                    <span className={`badge ${scheduler.enabled ? 'badge-approved' : 'badge-rejected'}`}>
                      {scheduler.enabled ? '● Active' : '○ Disabled'}
                    </span>
                    <span className="text-muted">task {scheduler.taskActive ? 'running' : 'stopped'}</span>
                  </div>
                  <table style={{ width: '100%' }}>
                    <tbody>
                      {[
                        ['Cron expression', scheduler.cronExpression],
                        ['Reminder interval', `${scheduler.reminderIntervalHours}h`],
                        ['Max reminders', scheduler.maxReminders],
                      ].map(([k, v]) => (
                        <tr key={k}>
                          <td className="text-muted text-sm" style={{ paddingBottom: 8 }}>{k}</td>
                          <td className="text-sm font-bold" style={{ paddingBottom: 8 }}>{v}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <Link to="/settings" className="btn btn-outline btn-sm mt-4">Configure →</Link>
                </div>
              ) : <div className="loading-center"><div className="spinner" /></div>}
            </div>
          )}

          {/* ── Recent approvals ── */}
          <div className="card">
            <div className="section-header mb-4">
              <div className="section-title">Recent Approvals</div>
              <Link to="/approvals" className="btn btn-outline btn-sm">View All →</Link>
            </div>
            {recent.length === 0
              ? <div className="empty-state"><div className="empty-icon">📭</div><p>No approval requests yet</p></div>
              : recent.map(r => (
                  <div key={r._id} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid #f1f5f9' }}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold" style={{ color: '#1e293b' }}>{r.documentName}</span>
                      <span className={`badge badge-${r.status}`}>{r.status.replace('_', ' ')}</span>
                    </div>
                    <div className="text-muted" style={{ marginTop: 4 }}>
                      {r.approvedCount}/{r.requiredApprovals} approved · by {r.submittedBy}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <div className="progress-bar">
                        <div
                          className={`progress-fill ${r.status === 'approved' ? 'green' : r.status === 'rejected' ? 'red' : 'blue'}`}
                          style={{ width: `${(r.approvedCount / r.requiredApprovals) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))
            }
          </div>
        </div>
      </div>
    </>
  );
}
