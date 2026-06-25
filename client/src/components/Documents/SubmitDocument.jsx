import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { listFiles, uploadFile, submitDocument, getConfig } from '../../services/api';

const EMPTY_STAKEHOLDER = { name: '', email: '' };

// Editable document formats only — no PDFs, images, archives, etc.
const ALLOWED_EXTENSIONS = ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'rtf', 'odt', 'ods', 'odp'];
const ALLOWED_ACCEPT = ALLOWED_EXTENSIONS.map(e => `.${e}`).join(',');
const ALLOWED_LABEL  = ALLOWED_EXTENSIONS.map(e => `.${e}`).join('  ');

function formatBytes(bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function SubmitDocument() {
  const nav = useNavigate();

  // document selection
  const [tab, setTab]               = useState('url');
  const [files, setFiles]           = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [folder, setFolder]         = useState('');
  const [loadingFiles, setLoadingFiles] = useState(false);

  // drag-and-drop upload
  const [dragging, setDragging]     = useState(false);
  const [uploading, setUploading]   = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadedFile, setUploadedFile] = useState(null); // file returned from API
  const dropRef                     = useRef(null);
  const fileInputRef                = useRef(null);

  // manual entry
  const [manualName, setManualName] = useState('');
  const [manualPath, setManualPath] = useState('');
  const [manualWebUrl, setManualWebUrl] = useState('');
  const [storageType, setStorageType] = useState('onedrive');

  // url link entry
  const [urlDocName, setUrlDocName] = useState('');
  const [urlLink, setUrlLink]       = useState('');

  // submission
  const [stakeholders, setStakeholders] = useState([
    { ...EMPTY_STAKEHOLDER },
    { ...EMPTY_STAKEHOLDER },
    { ...EMPTY_STAKEHOLDER }
  ]);
  const [submittedBy, setSubmittedBy]         = useState('');
  const [submittedByEmail, setSubmittedByEmail] = useState('');
  const [notes, setNotes]                     = useState('');
  const [reminderIntervalHours, setReminderIntervalHours] = useState(24);
  const [maxReminders, setMaxReminders]       = useState(3);
  const [submitting, setSubmitting]           = useState(false);
  const [error, setError]                     = useState('');

  useEffect(() => {
    getConfig().then(r => {
      const cfg = r.data;
      setStorageType(cfg.storage?.type || 'onedrive');
      setReminderIntervalHours(cfg.scheduler?.reminderIntervalHours || 24);
      setMaxReminders(cfg.scheduler?.maxReminders || 3);
    }).catch(() => {});
  }, []);

  // ── Browse storage ─────────────────────────────────────────────────────────
  async function handleBrowse() {
    setLoadingFiles(true); setError('');
    try {
      const res = await listFiles(folder || undefined);
      setFiles(res.data.files || []);
    } catch (e) { setError(e.message); }
    finally { setLoadingFiles(false); }
  }

  // ── Drag-and-drop handlers ─────────────────────────────────────────────────
  const onDragOver = useCallback(e => { e.preventDefault(); setDragging(true); }, []);
  const onDragLeave = useCallback(e => {
    if (!dropRef.current?.contains(e.relatedTarget)) setDragging(false);
  }, []);
  const onDrop = useCallback(e => {
    e.preventDefault(); setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }, [folder]); // eslint-disable-line

  async function handleUpload(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setError(`".${ext}" files are not allowed. Please upload an editable document: ${ALLOWED_LABEL}`);
      return;
    }
    setUploading(true); setUploadProgress(0); setError(''); setUploadedFile(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      if (folder) fd.append('folder', folder);

      const res = await uploadFile(fd, pct => setUploadProgress(pct));
      const uploaded = res.data.file;
      setUploadedFile(uploaded);
      setSelectedFile(uploaded);           // auto-select after upload
      setFiles(prev => {
        const exists = prev.find(f => f.fileId === uploaded.fileId);
        return exists ? prev : [uploaded, ...prev];
      });
    } catch (e) { setError(`Upload failed: ${e.message}`); }
    finally { setUploading(false); }
  }

  function handleFileInputChange(e) {
    const file = e.target.files[0];
    if (file) handleUpload(file);
    e.target.value = '';
  }

  // ── Stakeholders ───────────────────────────────────────────────────────────
  function updateStakeholder(idx, field, val) {
    setStakeholders(prev => prev.map((s, i) => i === idx ? { ...s, [field]: val } : s));
  }

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit(e) {
    e.preventDefault(); setError('');

    for (let i = 0; i < stakeholders.length; i++) {
      const s = stakeholders[i];
      if (!s.name.trim() || !s.email.trim()) { setError(`Stakeholder ${i + 1}: name and email required`); return; }
      if (!/\S+@\S+\.\S+/.test(s.email)) { setError(`Stakeholder ${i + 1}: invalid email`); return; }
    }
    const emails = stakeholders.map(s => s.email.toLowerCase());
    if (new Set(emails).size !== emails.length) { setError('Each stakeholder needs a unique email'); return; }

    let docData;
    if (tab === 'browse') {
      if (!selectedFile) { setError('Select or upload a file first'); return; }
      docData = { name: selectedFile.name, path: selectedFile.path, storageType: selectedFile.storageType,
        fileId: selectedFile.fileId, driveId: selectedFile.driveId, siteId: selectedFile.siteId,
        webUrl: selectedFile.webUrl, mimeType: selectedFile.mimeType, fileSize: selectedFile.fileSize };
    } else if (tab === 'manual') {
      if (!manualName.trim()) { setError('Document name is required'); return; }
      docData = { name: manualName, path: manualPath || '/', storageType, webUrl: manualWebUrl };
    } else {
      // url tab
      if (!urlDocName.trim()) { setError('Document name is required'); return; }
      if (!urlLink.trim())    { setError('Document URL is required'); return; }
      docData = { name: urlDocName, path: '/', storageType: 'external', webUrl: urlLink };
    }

    setSubmitting(true);
    try {
      await submitDocument({ ...docData, submittedBy, submittedByEmail, stakeholders, notes,
        reminderConfig: { intervalHours: +reminderIntervalHours, maxReminders: +maxReminders } });
      nav('/approvals');
    } catch (e) { setError(e.message); }
    finally { setSubmitting(false); }
  }

  const fileIcon = name => {
    const ext = name?.split('.').pop()?.toLowerCase();
    const map = { pdf: '📕', docx: '📘', doc: '📘', xlsx: '📗', xls: '📗', pptx: '📙', ppt: '📙',
      png: '🖼️', jpg: '🖼️', jpeg: '🖼️', zip: '🗜️', txt: '📄', csv: '📊' };
    return map[ext] || '📄';
  };

  return (
    <>
      <div className="page-header">
        <div><h1>Submit Document for Approval</h1><p>Select a document and assign 3 stakeholders</p></div>
      </div>
      <div className="page-body">
        {error && <div className="alert alert-error">⚠️ {error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="grid-2" style={{ alignItems: 'start' }}>

            {/* ── LEFT: Document ── */}
            <div>
              <div className="card mb-4">
                <div className="section-title mb-4">📄 Select Document</div>

                <div className="tabs">
                  <div className={`tab ${tab === 'browse' ? 'active' : ''}`} onClick={() => setTab('browse')}>Browse Storage</div>
                  <div className={`tab ${tab === 'url' ? 'active' : ''}`} onClick={() => setTab('url')}>🔗 URL Link</div>
                </div>

                {tab === 'browse' ? (
                  <>
                    {/* Folder path + browse button */}
                    <div className="flex gap-2 mb-4">
                      <input className="form-input" placeholder="Folder path (e.g. /Reports)"
                        value={folder} onChange={e => setFolder(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), handleBrowse())} />
                      <button type="button" className="btn btn-outline" onClick={handleBrowse} disabled={loadingFiles}>
                        {loadingFiles ? '…' : '🔍'}
                      </button>
                    </div>

                    {/* ── Drag-and-drop zone ── */}
                    <div
                      ref={dropRef}
                      onDragOver={onDragOver}
                      onDragLeave={onDragLeave}
                      onDrop={onDrop}
                      style={{
                        border: `2px dashed ${dragging ? '#2563eb' : uploadedFile ? '#16a34a' : '#cbd5e1'}`,
                        borderRadius: 10,
                        padding: '24px 16px',
                        textAlign: 'center',
                        background: dragging ? '#eff6ff' : uploadedFile ? '#f0fdf4' : '#f8fafc',
                        transition: 'all 0.2s',
                        marginBottom: 16,
                        cursor: 'pointer'
                      }}
                      onClick={() => !uploading && fileInputRef.current?.click()}
                    >
                      <input ref={fileInputRef} type="file" style={{ display: 'none' }}
                        accept={ALLOWED_ACCEPT}
                        onChange={handleFileInputChange} />

                      {uploading ? (
                        <>
                          <div style={{ fontSize: 32, marginBottom: 8 }}>⬆️</div>
                          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 12 }}>
                            Uploading to {storageType === 'sharepoint' ? 'SharePoint' : 'OneDrive'}…
                          </div>
                          <div style={{ background: '#e2e8f0', borderRadius: 999, height: 8, overflow: 'hidden', maxWidth: 300, margin: '0 auto' }}>
                            <div style={{ width: `${uploadProgress}%`, height: '100%', background: '#2563eb',
                              borderRadius: 999, transition: 'width 0.3s' }} />
                          </div>
                          <div style={{ color: '#64748b', fontSize: 13, marginTop: 8 }}>{uploadProgress}%</div>
                        </>
                      ) : uploadedFile ? (
                        <>
                          <div style={{ fontSize: 36, marginBottom: 6 }}>✅</div>
                          <div style={{ fontWeight: 700, color: '#16a34a', marginBottom: 4 }}>Uploaded successfully!</div>
                          <div style={{ color: '#1e293b', fontWeight: 600 }}>{fileIcon(uploadedFile.name)} {uploadedFile.name}</div>
                          <div style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>{formatBytes(uploadedFile.fileSize)}</div>
                          <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 4 }}>Drop or click to replace</div>
                        </>
                      ) : dragging ? (
                        <>
                          <div style={{ fontSize: 40, marginBottom: 8 }}>📂</div>
                          <div style={{ fontWeight: 700, color: '#2563eb', fontSize: 16 }}>Drop to upload</div>
                        </>
                      ) : (
                        <>
                          <div style={{ fontSize: 36, marginBottom: 8 }}>☁️</div>
                          <div style={{ fontWeight: 600, color: '#475569', marginBottom: 4 }}>
                            Drag & drop a file here
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: 13 }}>
                            or <span style={{ color: '#2563eb', textDecoration: 'underline', cursor: 'pointer' }}>click to browse</span> your computer
                          </div>
                          <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 6 }}>
                            Uploads to {storageType === 'sharepoint' ? 'SharePoint' : 'OneDrive'}
                            {folder ? ` › ${folder}` : ' (default folder)'}
                          </div>
                          <div style={{ color: '#cbd5e1', fontSize: 11, marginTop: 4 }}>
                            Allowed: .docx .doc .xlsx .xls .pptx .ppt .txt .csv .rtf .odt
                          </div>
                        </>
                      )}
                    </div>

                    {/* Existing files list from storage */}
                    {loadingFiles && <div className="loading-center"><div className="spinner" /></div>}

                    {!loadingFiles && files.length > 0 && (
                      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                        <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          Files in storage
                        </div>
                        {files.map(f => (
                          <div key={f.fileId}
                            className={`file-item ${selectedFile?.fileId === f.fileId ? 'selected' : ''}`}
                            onClick={() => setSelectedFile(f)}>
                            <span className="file-icon">{fileIcon(f.name)}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <div className="file-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
                              <div className="file-meta">{f.storageType} · {formatBytes(f.fileSize)}</div>
                            </div>
                            {selectedFile?.fileId === f.fileId && <span style={{ color: '#16a34a', fontSize: 18 }}>✅</span>}
                          </div>
                        ))}
                      </div>
                    )}

                    {!loadingFiles && files.length === 0 && !uploadedFile && (
                      <div className="empty-state" style={{ padding: '16px 0' }}>
                        <p style={{ fontSize: 13 }}>
                          Click 🔍 to browse existing files, or drag & drop to upload a new one
                        </p>
                      </div>
                    )}

                    {selectedFile && (
                      <div className="alert alert-info" style={{ marginTop: 12 }}>
                        <strong>Selected:</strong> {fileIcon(selectedFile.name)} {selectedFile.name}
                        {selectedFile.webUrl && (
                          <a href={selectedFile.webUrl} target="_blank" rel="noreferrer"
                            style={{ marginLeft: 8, color: '#1d4ed8', fontSize: 12 }}>View →</a>
                        )}
                      </div>
                    )}
                  </>
                ) : tab === 'manual' ? (
                  /* ── Manual entry tab ── */
                  <>
                    <div className="form-group">
                      <label className="form-label">Storage Type</label>
                      <div className="toggle-group">
                        {['onedrive', 'sharepoint'].map(t => (
                          <button type="button" key={t}
                            className={`toggle-btn ${storageType === t ? `active-${t}` : ''}`}
                            onClick={() => setStorageType(t)}>
                            {t === 'onedrive' ? '☁️ OneDrive' : '🏢 SharePoint'}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Document Name <span className="required">*</span></label>
                      <input className="form-input" value={manualName} onChange={e => setManualName(e.target.value)} placeholder="e.g. Q4 Budget Report.xlsx" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Folder Path</label>
                      <input className="form-input" value={manualPath} onChange={e => setManualPath(e.target.value)} placeholder="/Documents/Finance" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Document Web URL</label>
                      <input className="form-input" type="url" value={manualWebUrl} onChange={e => setManualWebUrl(e.target.value)} placeholder="https://..." />
                      <div className="form-hint">Shared with stakeholders in the approval email</div>
                    </div>
                  </>
                ) : (
                  /* ── URL Link tab ── */
                  <>
                    <div style={{ padding: '12px 0 8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20,
                        background: '#f0f9ff', border: '1px solid #bae6fd', borderRadius: 8, padding: '10px 14px' }}>
                        <span style={{ fontSize: 20 }}>🔗</span>
                        <span style={{ fontSize: 13, color: '#0369a1' }}>
                          Paste any document URL — it will be shared with stakeholders in the approval email.
                          No upload or storage connection required.
                        </span>
                      </div>
                    </div>
                    <div className="form-group">
                      <label className="form-label">Document Name <span className="required">*</span></label>
                      <input className="form-input"
                        value={urlDocName}
                        onChange={e => setUrlDocName(e.target.value)}
                        placeholder="e.g. Q4 Budget Report.xlsx" />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Document URL <span className="required">*</span></label>
                      <input className="form-input"
                        value={urlLink}
                        onChange={e => setUrlLink(e.target.value)}
                        placeholder="https://..." />
                    </div>
                  </>
                )}
              </div>

              {/* Reminder config */}
              <div className="card">
                <div className="section-title mb-4">⏰ Reminder Settings</div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Interval (hours)</label>
                    <input className="form-input" type="number" min="1" max="720"
                      value={reminderIntervalHours} onChange={e => setReminderIntervalHours(e.target.value)} />
                    <div className="form-hint">How often to re-send if no response</div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Max Reminders</label>
                    <input className="form-input" type="number" min="1" max="20"
                      value={maxReminders} onChange={e => setMaxReminders(e.target.value)} />
                    <div className="form-hint">Stop after this many reminders</div>
                  </div>
                </div>
              </div>
            </div>

            {/* ── RIGHT: Submitter + Stakeholders ── */}
            <div>
              <div className="card mb-4">
                <div className="section-title mb-4">👤 Submitted By</div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Your Name <span className="required">*</span></label>
                    <input className="form-input" value={submittedBy} onChange={e => setSubmittedBy(e.target.value)} placeholder="John Smith" required />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Your Email <span className="required">*</span></label>
                    <input className="form-input" type="email" value={submittedByEmail} onChange={e => setSubmittedByEmail(e.target.value)} placeholder="john@company.com" required />
                    <div className="form-hint">Completion notification sent here</div>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Notes</label>
                  <textarea className="form-textarea" value={notes} onChange={e => setNotes(e.target.value)} placeholder="Any notes for approvers…" />
                </div>
              </div>

              <div className="card">
                <div className="section-title mb-4">👥 Stakeholders (3 required)</div>
                {stakeholders.map((s, i) => (
                  <div key={i} style={{ marginBottom: 20 }}>
                    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                      <span className="stakeholder-num">{i + 1}</span>
                      <span className="text-sm font-bold" style={{ color: '#374151' }}>Stakeholder {i + 1}</span>
                    </div>
                    <div className="form-row">
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <input className="form-input" placeholder="Full name"
                          value={s.name} onChange={e => updateStakeholder(i, 'name', e.target.value)} required />
                      </div>
                      <div className="form-group" style={{ marginBottom: 0 }}>
                        <input className="form-input" type="email" placeholder="email@company.com"
                          value={s.email} onChange={e => updateStakeholder(i, 'email', e.target.value)} required />
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6">
                <button type="submit" className="btn btn-primary btn-lg w-full" disabled={submitting || uploading}>
                  {submitting ? '⏳ Submitting…' : uploading ? '⏳ Upload in progress…' : '🚀 Submit for Approval'}
                </button>
              </div>
              <div className="text-muted text-sm mt-4" style={{ textAlign: 'center' }}>
                Approval emails will be sent immediately to all 3 stakeholders
              </div>
            </div>

          </div>
        </form>
      </div>
    </>
  );
}
