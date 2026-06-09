import React, { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { getApprovalByToken, respondToApproval } from '../../services/api';

export default function ApprovalPage() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const autoAction = searchParams.get('action'); // 'approve' | 'reject'

  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [action, setAction] = useState('');
  const [comments, setComments] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    getApprovalByToken(token)
      .then(r => {
        setInfo(r.data);
        // Pre-select action from URL param
        if (autoAction && r.data.status === 'pending') {
          setAction(autoAction);
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [token, autoAction]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!action) { setError('Please select Approve or Reject'); return; }
    setSubmitting(true);
    setError('');
    try {
      const res = await respondToApproval(token, { action, comments });
      setResult(res.data);
      setDone(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return (
    <div className="approval-page">
      <div className="approval-card">
        <div className="loading-center" style={{ padding: 80 }}>
          <div className="spinner" />
          <span>Loading approval request…</span>
        </div>
      </div>
    </div>
  );

  if (error && !info) return (
    <div className="approval-page">
      <div className="approval-card">
        <div className="approval-header red">
          <h1>Invalid Link</h1>
          <p>This approval link is invalid or has expired</p>
        </div>
        <div className="approval-body">
          <div className="alert alert-error">{error}</div>
        </div>
      </div>
    </div>
  );

  if (info?.status !== 'pending') return (
    <div className="approval-page">
      <div className="approval-card">
        <div className={`approval-header ${info.status === 'approved' ? 'green' : 'orange'}`}>
          <h1>{info.status === 'approved' ? '✅ Already Approved' : '🔒 Already Responded'}</h1>
          <p>You have already responded to this request</p>
        </div>
        <div className="approval-body">
          <p style={{ color: '#64748b', fontSize: 14, marginBottom: 12 }}>Document: <strong>{info.documentName}</strong></p>
          <p style={{ color: '#64748b', fontSize: 14 }}>Your response: <strong>{info.status}</strong></p>
          {info.requestStatus !== 'pending' && info.requestStatus !== 'in_progress' && (
            <div className="alert alert-info mt-4">
              Overall request status: <strong>{info.requestStatus}</strong>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  if (done) return (
    <div className="approval-page">
      <div className="approval-card">
        <div className={`approval-header ${result?.status === 'approved' ? 'green' : action === 'approve' ? 'green' : 'red'}`}>
          <h1>{action === 'approve' ? '✅ Approved!' : '❌ Rejected'}</h1>
          <p>Your response has been recorded</p>
        </div>
        <div className="approval-body">
          <p style={{ color: '#475569', fontSize: 15 }}>
            Thank you, <strong>{info.stakeholderName}</strong>. Your decision on <strong>"{info.documentName}"</strong> has been recorded.
          </p>
          {comments && (
            <div className="alert alert-info mt-4">
              Your comments: <em>"{comments}"</em>
            </div>
          )}
          {result?.status && (
            <div className={`alert mt-4 ${result.status === 'approved' ? 'alert-success' : result.status === 'rejected' ? 'alert-error' : 'alert-info'}`}>
              Overall document status is now: <strong>{result.status}</strong>
              {result.approvedCount !== undefined && ` (${result.approvedCount} of ${info.requiredApprovals || 3} approved)`}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="approval-page">
      <div className="approval-card">
        <div className="approval-header blue">
          <h1>Document Approval Required</h1>
          <p>Your review is needed</p>
        </div>

        <div className="approval-body">
          <p style={{ color: '#1e293b', fontSize: 15, marginBottom: 16 }}>
            Hi <strong>{info.stakeholderName}</strong>,
          </p>
          <p style={{ color: '#64748b', marginBottom: 20 }}>
            You have been asked to approve the following document:
          </p>

          <div style={{
            background: '#f1f5f9', borderLeft: '4px solid #2563eb',
            padding: 16, borderRadius: 4, marginBottom: 24
          }}>
            <div style={{ fontSize: 12, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 6 }}>Document</div>
            <div style={{ fontWeight: 700, fontSize: 18, color: '#0f172a' }}>{info.documentName}</div>
            <div style={{ marginTop: 6, color: '#64748b', fontSize: 13 }}>Submitted by: {info.submittedBy}</div>
            {info.documentWebUrl && (
              <div style={{ marginTop: 8 }}>
                <a href={info.documentWebUrl} target="_blank" rel="noreferrer" style={{ color: '#2563eb', fontSize: 13 }}>
                  View document →
                </a>
              </div>
            )}
          </div>

          {error && <div className="alert alert-error mb-4">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Your Decision <span className="required">*</span></label>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setAction('approve')}
                  style={{
                    flex: 1, padding: '14px', border: '2px solid',
                    borderColor: action === 'approve' ? '#16a34a' : '#e2e8f0',
                    background: action === 'approve' ? '#f0fdf4' : '#fff',
                    borderRadius: 8, cursor: 'pointer', fontSize: 16, fontWeight: 600,
                    color: action === 'approve' ? '#16a34a' : '#64748b',
                    transition: 'all 0.15s'
                  }}
                >
                  ✓ Approve
                </button>
                <button
                  type="button"
                  onClick={() => setAction('reject')}
                  style={{
                    flex: 1, padding: '14px', border: '2px solid',
                    borderColor: action === 'reject' ? '#dc2626' : '#e2e8f0',
                    background: action === 'reject' ? '#fef2f2' : '#fff',
                    borderRadius: 8, cursor: 'pointer', fontSize: 16, fontWeight: 600,
                    color: action === 'reject' ? '#dc2626' : '#64748b',
                    transition: 'all 0.15s'
                  }}
                >
                  ✗ Reject
                </button>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Comments (optional)</label>
              <textarea
                className="form-textarea"
                value={comments}
                onChange={e => setComments(e.target.value)}
                placeholder="Add any comments or reasons for your decision…"
              />
            </div>

            <button type="submit" className={`btn w-full btn-lg ${action === 'approve' ? 'btn-success' : action === 'reject' ? 'btn-danger' : 'btn-primary'}`} disabled={submitting || !action}>
              {submitting ? '⏳ Submitting…' : action === 'approve' ? '✓ Confirm Approval' : action === 'reject' ? '✗ Confirm Rejection' : 'Select a decision above'}
            </button>
          </form>
        </div>

        <div className="approval-footer" style={{ justifyContent: 'center' }}>
          <span style={{ fontSize: 12, color: '#94a3b8' }}>
            Document Approval Workflow System
          </span>
        </div>
      </div>
    </div>
  );
}
