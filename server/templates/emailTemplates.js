const baseStyle = `
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #f4f6f9;
  padding: 40px 20px;
`;

const cardStyle = `
  max-width: 600px;
  margin: 0 auto;
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
`;

const headerStyle = (color = '#2563eb') => `
  background: ${color};
  padding: 32px 40px;
  text-align: center;
`;

const bodyStyle = `padding: 40px;`;

const btnStyle = (color = '#2563eb') => `
  display: inline-block;
  padding: 14px 32px;
  background: ${color};
  color: #ffffff !important;
  text-decoration: none;
  border-radius: 6px;
  font-weight: 600;
  font-size: 15px;
  margin: 8px;
`;

const footerStyle = `
  text-align: center;
  padding: 24px 40px;
  background: #f8fafc;
  color: #94a3b8;
  font-size: 12px;
  border-top: 1px solid #e2e8f0;
`;

// ─── Approval Request ───────────────────────────────────────────────────────
function approvalRequestTemplate({ stakeholderName, documentName, documentWebUrl, approveUrl, rejectUrl, changesUrl, submittedBy, appUrl, reminderIntervalHours, amendment }) {
  const amendmentBanner = amendment ? `
      <div style="background:#fef3c7;border-left:4px solid #d97706;padding:20px;border-radius:4px;margin:0 0 24px 0;">
        <p style="margin:0 0 6px 0;color:#92400e;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">⚠️ Document Amended — Re-review Required</p>
        <p style="margin:0 0 4px 0;color:#1e293b;font-size:14px;">This document was amended by <strong>${amendment.changedBy}</strong> (${amendment.changedByEmail}).</p>
        ${amendment.comments ? `<p style="margin:8px 0 0 0;color:#475569;font-size:14px;"><strong>What changed:</strong> ${amendment.comments}</p>` : ''}
      </div>` : '';

  return {
    subject: amendment
      ? `Re-review Required: "${documentName}" has been amended`
      : `Action Required: Approval needed for "${documentName}"`,
    html: `
<div style="${baseStyle}">
  <div style="${cardStyle}">
    <div style="${headerStyle('#2563eb')}">
      <h1 style="color:#fff;margin:0;font-size:24px;">Document Approval Required</h1>
      <p style="color:#bfdbfe;margin:8px 0 0 0;font-size:14px;">Your review is needed</p>
    </div>
    <div style="${bodyStyle}">
      ${amendmentBanner}
      <p style="color:#1e293b;font-size:16px;">Hi <strong>${stakeholderName}</strong>,</p>
      <p style="color:#475569;">${amendment ? 'The document listed below has been amended and requires your re-review:' : 'You have been requested to review and approve the following document:'}</p>

      <div style="background:#f1f5f9;border-left:4px solid #2563eb;padding:20px;border-radius:4px;margin:24px 0;">
        <p style="margin:0 0 8px 0;color:#64748b;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;">Document</p>
        <p style="margin:0;color:#1e293b;font-size:18px;font-weight:600;">${documentName}</p>
        ${documentWebUrl ? `<p style="margin:8px 0 0 0;"><a href="${documentWebUrl}" style="color:#2563eb;font-size:13px;">View document in SharePoint/OneDrive →</a></p>` : ''}
        <p style="margin:8px 0 0 0;color:#64748b;font-size:13px;">Submitted by: <strong>${submittedBy}</strong></p>
      </div>

      <p style="color:#475569;">Please click one of the buttons below to respond:</p>

      <div style="text-align:center;margin:32px 0;">
        <a href="${approveUrl}" style="${btnStyle('#16a34a')}">✓ Approve</a>
        <a href="${rejectUrl}" style="${btnStyle('#dc2626')}">✗ Reject</a>
        <br/>
        <a href="${changesUrl}" style="${btnStyle('#7c3aed')}">✏️ Amend</a>
      </div>

      <p style="color:#94a3b8;font-size:13px;text-align:center;">
        If you don't respond, you will receive a reminder every ${reminderIntervalHours} hour(s).
      </p>
    </div>
    <div style="${footerStyle}">
      <p style="margin:0;">Document Approval System · <a href="${appUrl}" style="color:#2563eb;">Open Dashboard</a></p>
    </div>
  </div>
</div>`
  };
}

// ─── Reminder ───────────────────────────────────────────────────────────────
function reminderTemplate({ stakeholderName, documentName, documentWebUrl, approveUrl, rejectUrl, changesUrl, submittedBy, appUrl, reminderNumber, maxReminders }) {
  return {
    subject: `Reminder ${reminderNumber}/${maxReminders}: Approval still needed for "${documentName}"`,
    html: `
<div style="${baseStyle}">
  <div style="${cardStyle}">
    <div style="${headerStyle('#d97706')}">
      <h1 style="color:#fff;margin:0;font-size:24px;">⏰ Approval Reminder</h1>
      <p style="color:#fef3c7;margin:8px 0 0 0;font-size:14px;">Reminder ${reminderNumber} of ${maxReminders}</p>
    </div>
    <div style="${bodyStyle}">
      <p style="color:#1e293b;font-size:16px;">Hi <strong>${stakeholderName}</strong>,</p>
      <p style="color:#475569;">This is a friendly reminder that your approval is still pending for:</p>

      <div style="background:#fffbeb;border-left:4px solid #d97706;padding:20px;border-radius:4px;margin:24px 0;">
        <p style="margin:0 0 8px 0;color:#92400e;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;">Document</p>
        <p style="margin:0;color:#1e293b;font-size:18px;font-weight:600;">${documentName}</p>
        ${documentWebUrl ? `<p style="margin:8px 0 0 0;"><a href="${documentWebUrl}" style="color:#d97706;font-size:13px;">View document →</a></p>` : ''}
        <p style="margin:8px 0 0 0;color:#64748b;font-size:13px;">Submitted by: <strong>${submittedBy}</strong></p>
      </div>

      <div style="text-align:center;margin:32px 0;">
        <a href="${approveUrl}" style="${btnStyle('#16a34a')}">✓ Approve</a>
        <a href="${rejectUrl}" style="${btnStyle('#dc2626')}">✗ Reject</a>
        <br/>
        <a href="${changesUrl}" style="${btnStyle('#7c3aed')}">✏️ Amend</a>
      </div>
    </div>
    <div style="${footerStyle}">
      <p style="margin:0;">Document Approval System · <a href="${appUrl}" style="color:#2563eb;">Open Dashboard</a></p>
    </div>
  </div>
</div>`
  };
}

// ─── Completion Notification (to submitter) ─────────────────────────────────
function completionTemplate({ submittedBy, documentName, documentWebUrl, status, approvals, appUrl }) {
  const isApproved = status === 'approved';
  const color = isApproved ? '#16a34a' : '#dc2626';
  const icon = isApproved ? '✅' : '❌';
  const title = isApproved ? 'Document Approved' : 'Document Rejected';
  const approvalsHtml = approvals.map(a => `
    <tr>
      <td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;">${a.name}</td>
      <td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;">${a.email}</td>
      <td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;">
        <span style="color:${a.status === 'approved' ? '#16a34a' : a.status === 'rejected' ? '#dc2626' : '#94a3b8'};font-weight:600;">
          ${a.status === 'approved' ? '✓ Approved' : a.status === 'rejected' ? '✗ Rejected' : '⏳ Pending'}
        </span>
      </td>
      <td style="padding:10px 16px;border-bottom:1px solid #f1f5f9;color:#64748b;font-size:13px;">${a.comments || '—'}</td>
    </tr>
  `).join('');

  return {
    subject: `${icon} "${documentName}" has been ${status}`,
    html: `
<div style="${baseStyle}">
  <div style="${cardStyle}">
    <div style="${headerStyle(color)}">
      <h1 style="color:#fff;margin:0;font-size:24px;">${icon} ${title}</h1>
    </div>
    <div style="${bodyStyle}">
      <p style="color:#1e293b;font-size:16px;">Hi <strong>${submittedBy}</strong>,</p>
      <p style="color:#475569;">The approval process for <strong>"${documentName}"</strong> has been completed.</p>
      ${documentWebUrl ? `<p><a href="${documentWebUrl}" style="color:#2563eb;">View document →</a></p>` : ''}

      <h3 style="color:#1e293b;margin-top:32px;">Approval Summary</h3>
      <table style="width:100%;border-collapse:collapse;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#f8fafc;">
            <th style="padding:12px 16px;text-align:left;color:#64748b;font-size:13px;">Name</th>
            <th style="padding:12px 16px;text-align:left;color:#64748b;font-size:13px;">Email</th>
            <th style="padding:12px 16px;text-align:left;color:#64748b;font-size:13px;">Decision</th>
            <th style="padding:12px 16px;text-align:left;color:#64748b;font-size:13px;">Comments</th>
          </tr>
        </thead>
        <tbody>${approvalsHtml}</tbody>
      </table>

      <div style="text-align:center;margin-top:32px;">
        <a href="${appUrl}/approvals" style="${btnStyle('#2563eb')}">View in Dashboard</a>
      </div>
    </div>
    <div style="${footerStyle}">
      <p style="margin:0;">Document Approval System</p>
    </div>
  </div>
</div>`
  };
}

// ─── Document Updated Notification (to submitter) ───────────────────────────
function documentUpdatedTemplate({ submittedBy, documentName, documentWebUrl, changedBy, changedByEmail, comments, appUrl }) {
  return {
    subject: `✏️ "${documentName}" has been updated — re-review needed`,
    html: `
<div style="${baseStyle}">
  <div style="${cardStyle}">
    <div style="${headerStyle('#7c3aed')}">
      <h1 style="color:#fff;margin:0;font-size:24px;">✏️ Document Updated</h1>
      <p style="color:#ede9fe;margin:8px 0 0 0;font-size:14px;">Re-review is needed</p>
    </div>
    <div style="${bodyStyle}">
      <p style="color:#1e293b;font-size:16px;">Hi <strong>${submittedBy}</strong>,</p>
      <p style="color:#475569;">A stakeholder has indicated that <strong>"${documentName}"</strong> has been updated and requires re-review.</p>

      <div style="background:#f5f3ff;border-left:4px solid #7c3aed;padding:20px;border-radius:4px;margin:24px 0;">
        <p style="margin:0 0 8px 0;color:#5b21b6;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;">Updated By</p>
        <p style="margin:0;color:#1e293b;font-size:16px;font-weight:600;">${changedBy}</p>
        <p style="margin:4px 0 0 0;color:#64748b;font-size:13px;">${changedByEmail}</p>
        ${comments ? `<p style="margin:12px 0 0 0;color:#475569;font-size:14px;"><strong>Note:</strong> ${comments}</p>` : ''}
      </div>

      <p style="color:#475569;">All stakeholders have been sent new approval emails with updated links. Please ensure the latest version of the document is available before they review it.</p>
      ${documentWebUrl ? `<p><a href="${documentWebUrl}" style="color:#7c3aed;">View document →</a></p>` : ''}

      <div style="text-align:center;margin-top:32px;">
        <a href="${appUrl}/approvals" style="${btnStyle('#7c3aed')}">View in Dashboard</a>
      </div>
    </div>
    <div style="${footerStyle}">
      <p style="margin:0;">Document Approval System</p>
    </div>
  </div>
</div>`
  };
}

// ─── Test Email ──────────────────────────────────────────────────────────────
function testEmailTemplate({ provider }) {
  return {
    subject: 'Email Configuration Test — Document Approval System',
    html: `
<div style="${baseStyle}">
  <div style="${cardStyle}">
    <div style="${headerStyle('#7c3aed')}">
      <h1 style="color:#fff;margin:0;font-size:24px;">✅ Email Config Works!</h1>
    </div>
    <div style="${bodyStyle}">
      <p style="color:#1e293b;font-size:16px;">Your <strong>${provider.toUpperCase()}</strong> email configuration is working correctly.</p>
      <p style="color:#475569;">The Document Approval System is ready to send notifications.</p>
    </div>
    <div style="${footerStyle}">
      <p style="margin:0;">Document Approval System</p>
    </div>
  </div>
</div>`
  };
}

module.exports = {
  approvalRequestTemplate,
  reminderTemplate,
  completionTemplate,
  documentUpdatedTemplate,
  testEmailTemplate
};
