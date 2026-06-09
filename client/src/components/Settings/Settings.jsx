import React, { useEffect, useState } from 'react';
import { getConfig, updateConfig, testEmail, testStorage, runSchedulerNow } from '../../services/api';

export default function Settings() {
  const [cfg, setCfg]                       = useState(null);
  const [loading, setLoading]               = useState(true);
  const [saving, setSaving]                 = useState(false);
  const [testing, setTesting]               = useState(false);
  const [testingStorage, setTestingStorage] = useState(false);
  const [runningScheduler, setRunningScheduler] = useState(false);
  const [testEmailAddr, setTestEmailAddr]   = useState('');
  const [msg, setMsg]                       = useState({ type: '', text: '' });
  const [activeTab, setActiveTab]           = useState('email');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const res = await getConfig();
      setCfg(res.data);
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setLoading(false); }
  }

  // Deep-set a dotted path: set('ms365.tenantId', val)
  function set(path, val) {
    setCfg(prev => {
      const next  = { ...prev };
      const parts = path.split('.');
      let obj = next;
      for (let i = 0; i < parts.length - 1; i++) {
        obj[parts[i]] = { ...obj[parts[i]] };
        obj = obj[parts[i]];
      }
      obj[parts[parts.length - 1]] = val;
      return next;
    });
  }

  async function handleSave(e) {
    e?.preventDefault();
    setSaving(true);
    setMsg({ type: '', text: '' });
    try {
      await updateConfig(cfg);
      setMsg({ type: 'success', text: '✅ Configuration saved successfully.' });
      load();
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setSaving(false); }
  }

  async function handleTestEmail() {
    if (!testEmailAddr) { setMsg({ type: 'error', text: 'Enter a recipient email address' }); return; }
    setTesting(true);
    setMsg({ type: '', text: '' });
    try {
      await updateConfig(cfg);          // save first
      await testEmail(testEmailAddr);
      setMsg({ type: 'success', text: `✅ Test email sent to ${testEmailAddr} via Microsoft 365` });
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setTesting(false); }
  }

  async function handleTestStorage() {
    setTestingStorage(true);
    setMsg({ type: '', text: '' });
    try {
      await updateConfig(cfg);          // save first
      const res = await testStorage();
      const d = res.data;
      setMsg({ type: 'success', text: `✅ Storage connected! Site: "${d.siteName || d.driveName || d.storageType}"` });
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setTestingStorage(false); }
  }

  async function handleRunScheduler() {
    setRunningScheduler(true);
    setMsg({ type: '', text: '' });
    try {
      await runSchedulerNow();
      setMsg({ type: 'success', text: '✅ Scheduler ran — pending reminders processed.' });
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally { setRunningScheduler(false); }
  }

  if (loading) return (
    <>
      <div className="page-header"><div><h1>Settings</h1></div></div>
      <div className="loading-center"><div className="spinner" /></div>
    </>
  );

  return (
    <>
      <div className="page-header">
        <div><h1>Settings</h1><p>Configure Microsoft 365, scheduler, and storage</p></div>
        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? '⏳ Saving…' : '💾 Save All'}
        </button>
      </div>

      <div className="page-body">
        {msg.text && (
          <div className={`alert alert-${msg.type === 'error' ? 'error' : 'success'}`}>
            {msg.text}
            <button style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer' }}
              onClick={() => setMsg({ type: '', text: '' })}>✕</button>
          </div>
        )}

        <div className="tabs">
          {[
            ['email',     '📧 Email (MS365)'],
            ['scheduler', '⏰ Scheduler'],
            ['storage',   '☁️ Storage'],
            ['general',   '⚙️ General'],
          ].map(([id, label]) => (
            <div key={id} className={`tab ${activeTab === id ? 'active' : ''}`}
              onClick={() => setActiveTab(id)}>{label}</div>
          ))}
        </div>

        <form onSubmit={handleSave}>

          {/* ── EMAIL ─────────────────────────────────────────────────── */}
          {activeTab === 'email' && (
            <div style={{ maxWidth: 680 }}>
              <div className="card mb-4">
                <div className="section-title mb-2">🏢 Microsoft 365 — Graph API</div>
                <div className="alert alert-info mb-4" style={{ fontSize: 13 }}>
                  Emails are sent via <strong>Microsoft Graph API</strong> using an Azure AD App Registration.
                  Required permission: <code>Mail.Send</code> (Application, admin-consented).
                  The <em>From Email</em> must be a licensed mailbox in your tenant.
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Tenant ID <span className="required">*</span></label>
                    <input className="form-input" value={cfg.ms365?.tenantId || ''}
                      onChange={e => set('ms365.tenantId', e.target.value)}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Client ID <span className="required">*</span></label>
                    <input className="form-input" value={cfg.ms365?.clientId || ''}
                      onChange={e => set('ms365.clientId', e.target.value)}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Client Secret <span className="required">*</span></label>
                  <input className="form-input" type="password" value={cfg.ms365?.clientSecret || ''}
                    onChange={e => set('ms365.clientSecret', e.target.value)}
                    placeholder="••••••••" />
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">From Email <span className="required">*</span></label>
                    <input className="form-input" type="email" value={cfg.ms365?.fromEmail || ''}
                      onChange={e => set('ms365.fromEmail', e.target.value)}
                      placeholder="no-reply@yourcompany.com" />
                    <div className="form-hint">Must be a licensed M365 mailbox</div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">From Name</label>
                    <input className="form-input" value={cfg.ms365?.fromName || ''}
                      onChange={e => set('ms365.fromName', e.target.value)}
                      placeholder="Document Approval System" />
                  </div>
                </div>
              </div>

              {/* Test email */}
              <div className="card">
                <div className="section-title mb-4">🧪 Send Test Email</div>
                <div className="flex gap-3">
                  <input className="form-input" type="email"
                    placeholder="Send test email to…"
                    value={testEmailAddr}
                    onChange={e => setTestEmailAddr(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleTestEmail()}
                  />
                  <button type="button" className="btn btn-outline" onClick={handleTestEmail} disabled={testing}>
                    {testing ? '⏳ Sending…' : '📨 Send Test'}
                  </button>
                </div>
                <div className="form-hint" style={{ marginTop: 8 }}>
                  Saves current settings first, then sends a test email via Microsoft 365
                </div>
              </div>
            </div>
          )}

          {/* ── SCHEDULER ─────────────────────────────────────────────── */}
          {activeTab === 'scheduler' && (
            <div style={{ maxWidth: 560 }}>
              <div className="card mb-4">
                <div className="section-title mb-4">Scheduler Configuration</div>

                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" checked={cfg.scheduler?.enabled ?? true}
                      onChange={e => set('scheduler.enabled', e.target.checked)} />
                    Enable automatic reminders
                  </label>
                  <div className="form-hint">
                    When enabled, the scheduler sends reminder emails on the cron schedule below
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Cron Expression</label>
                  <input className="form-input" value={cfg.scheduler?.cronExpression || '0 * * * *'}
                    onChange={e => set('scheduler.cronExpression', e.target.value)} />
                  <div className="form-hint">
                    <code>0 * * * *</code> every hour &nbsp;·&nbsp;
                    <code>0 9 * * 1-5</code> 9 AM Mon–Fri &nbsp;·&nbsp;
                    <code>0 */6 * * *</code> every 6 hours
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Reminder Interval (hours)</label>
                    <input className="form-input" type="number" min="1" max="720"
                      value={cfg.scheduler?.reminderIntervalHours ?? 24}
                      onChange={e => set('scheduler.reminderIntervalHours', +e.target.value)} />
                    <div className="form-hint">Min hours between reminders per person</div>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Max Reminders Per Person</label>
                    <input className="form-input" type="number" min="1" max="50"
                      value={cfg.scheduler?.maxReminders ?? 3}
                      onChange={e => set('scheduler.maxReminders', +e.target.value)} />
                    <div className="form-hint">Stop reminding after this many times</div>
                  </div>
                </div>
              </div>

              <div className="card">
                <div className="section-title mb-2">🧪 Test Scheduler</div>
                <p className="text-muted text-sm mb-4">
                  Immediately process all pending reminders (ignores the time-interval check).
                </p>
                <button type="button" className="btn btn-warning" onClick={handleRunScheduler} disabled={runningScheduler}>
                  {runningScheduler ? '⏳ Running…' : '▶ Run Scheduler Now'}
                </button>
              </div>
            </div>
          )}

          {/* ── STORAGE ───────────────────────────────────────────────── */}
          {activeTab === 'storage' && (
            <div style={{ maxWidth: 680 }}>
              <div className="card mb-4">
                <div className="section-title mb-4">Storage Location</div>
                <div className="toggle-group mb-4">
                  {['onedrive', 'sharepoint'].map(t => (
                    <button type="button" key={t}
                      className={`toggle-btn ${cfg.storage?.type === t ? `active-${t}` : ''}`}
                      onClick={() => set('storage.type', t)}>
                      {t === 'onedrive' ? '☁️ OneDrive' : '🏢 SharePoint'}
                    </button>
                  ))}
                </div>

                <div className="alert alert-info mb-4" style={{ fontSize: 13 }}>
                  Uses <strong>Microsoft Graph API</strong>. The same Azure AD App Registration used for email can be reused.
                  Required permissions: <code>Files.Read.All</code>
                  {cfg.storage?.type === 'sharepoint' && <>, <code>Sites.Read.All</code></>} (Application, admin-consented).
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Tenant ID <span className="required">*</span></label>
                    <input className="form-input" value={cfg.storage?.tenantId || ''}
                      onChange={e => set('storage.tenantId', e.target.value)}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Client ID <span className="required">*</span></label>
                    <input className="form-input" value={cfg.storage?.clientId || ''}
                      onChange={e => set('storage.clientId', e.target.value)}
                      placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Client Secret <span className="required">*</span></label>
                  <input className="form-input" type="password" value={cfg.storage?.clientSecret || ''}
                    onChange={e => set('storage.clientSecret', e.target.value)}
                    placeholder="••••••••" />
                </div>

                {cfg.storage?.type === 'onedrive' ? (
                  <div className="form-group">
                    <label className="form-label">Drive ID <span className="text-muted">(optional)</span></label>
                    <input className="form-input" value={cfg.storage?.driveId || ''}
                      onChange={e => set('storage.driveId', e.target.value)}
                      placeholder="Leave blank to use the default drive" />
                    <div className="form-hint">Find via Graph Explorer: <code>GET /drives</code></div>
                  </div>
                ) : (
                  <div className="form-group">
                    <label className="form-label">SharePoint Site URL <span className="required">*</span></label>
                    <input className="form-input" value={cfg.storage?.siteUrl || ''}
                      onChange={e => set('storage.siteUrl', e.target.value)}
                      placeholder="https://yourcompany.sharepoint.com/sites/yoursite" />
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label">Default Folder Path</label>
                  <input className="form-input" value={cfg.storage?.folderPath || '/'}
                    onChange={e => set('storage.folderPath', e.target.value)}
                    placeholder="/Documents" />
                </div>
              </div>

              <div className="card">
                <div className="section-title mb-2">🧪 Test Storage Connection</div>
                <p className="text-muted text-sm mb-4">
                  Saves settings then verifies access to your {cfg.storage?.type === 'sharepoint' ? 'SharePoint site' : 'OneDrive'}.
                </p>
                <button type="button" className="btn btn-outline" onClick={handleTestStorage} disabled={testingStorage}>
                  {testingStorage ? '⏳ Testing…' : '🔌 Test Connection'}
                </button>
              </div>
            </div>
          )}

          {/* ── GENERAL ───────────────────────────────────────────────── */}
          {activeTab === 'general' && (
            <div style={{ maxWidth: 480 }}>
              <div className="card">
                <div className="section-title mb-4">General Settings</div>
                <div className="form-group">
                  <label className="form-label">App URL</label>
                  <input className="form-input" value={cfg.appUrl || 'http://localhost:3000'}
                    onChange={e => set('appUrl', e.target.value)}
                    placeholder="http://localhost:3000" />
                  <div className="form-hint">
                    Used in email approval links. Set to your public domain in production.
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="mt-6">
            <button type="submit" className="btn btn-primary btn-lg" disabled={saving}>
              {saving ? '⏳ Saving…' : '💾 Save Settings'}
            </button>
          </div>
        </form>
      </div>
    </>
  );
}
