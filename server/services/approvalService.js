/**
 * approvalService.js
 * Handles creation, response processing, and status updates for approval requests.
 */

const { v4: uuidv4 } = require('uuid');
const ApprovalRequest = require('../models/ApprovalRequest');
const Document = require('../models/Document');
const Config = require('../models/Config');
const emailService = require('./emailService');
const {
  approvalRequestTemplate,
  completionTemplate
} = require('../templates/emailTemplates');

class ApprovalService {
  async _getConfig() {
    let cfg = await Config.findOne();
    if (!cfg) { cfg = new Config(); await cfg.save(); }
    return cfg;
  }

  // ── Create a new approval request ─────────────────────────────────────────

  /**
   * @param {Object} opts
   * @param {string} opts.documentId
   * @param {Array<{name,email}>} opts.stakeholders  — exactly 3
   * @param {string} opts.submittedBy
   * @param {string} opts.submittedByEmail
   * @param {string} opts.notes
   * @param {Object} opts.reminderConfig  { intervalHours, maxReminders }
   */
  async createApprovalRequest(opts) {
    const { documentId, stakeholders, submittedBy, submittedByEmail, notes, reminderConfig } = opts;

    const doc = await Document.findById(documentId);
    if (!doc) throw new Error('Document not found');

    const cfg = await this._getConfig();

    const approvals = stakeholders.map(s => ({
      name: s.name,
      email: s.email,
      status: 'pending',
      token: uuidv4(),
      reminderCount: 0
    }));

    const request = await ApprovalRequest.create({
      documentId,
      documentName: doc.name,
      documentWebUrl: doc.webUrl,
      approvals,
      requiredApprovals: stakeholders.length,
      submittedBy,
      submittedByEmail,
      notes: notes || '',
      status: 'pending',
      reminderConfig: {
        intervalHours: reminderConfig?.intervalHours || cfg.scheduler.reminderIntervalHours,
        maxReminders: reminderConfig?.maxReminders || cfg.scheduler.maxReminders
      }
    });

    // Update document status
    await Document.findByIdAndUpdate(documentId, {
      status: 'in_review',
      approvalRequestId: request._id
    });

    // Send initial approval emails
    await this._sendInitialEmails(request, cfg);

    return request;
  }

  // Wait helper
  _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // Send with retry on 429 (rate-limit) or 503 (throttle)
  async _sendWithRetry(emailOpts, maxRetries = 3, baseDelayMs = 2000) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        return await emailService.send(emailOpts);
      } catch (err) {
        const status = err.response?.status || err.statusCode;
        const retryable = status === 429 || status === 503 || status === 502;

        if (retryable && attempt < maxRetries) {
          // Honour Retry-After header if present, else use exponential backoff
          const retryAfter = err.response?.headers?.['retry-after'];
          const waitMs = retryAfter
            ? parseInt(retryAfter) * 1000
            : baseDelayMs * attempt;
          console.warn(`[Email] Rate-limited (${status}), retrying in ${waitMs}ms (attempt ${attempt}/${maxRetries})…`);
          await this._sleep(waitMs);
        } else {
          throw err; // non-retryable or max retries exhausted
        }
      }
    }
  }

  async _sendInitialEmails(request, cfg) {
    const appUrl = cfg.appUrl || 'http://localhost:3000';
    const results = [];

    for (let i = 0; i < request.approvals.length; i++) {
      const approval = request.approvals[i];

      // Small gap between each send to avoid MS365 throttling (1 req/sec safe zone)
      if (i > 0) await this._sleep(1500);

      const approveUrl = `${appUrl}/approve/${approval.token}?action=approve`;
      const rejectUrl  = `${appUrl}/approve/${approval.token}?action=reject`;

      const { subject, html } = approvalRequestTemplate({
        stakeholderName: approval.name,
        documentName: request.documentName,
        documentWebUrl: request.documentWebUrl,
        approveUrl,
        rejectUrl,
        submittedBy: request.submittedBy,
        appUrl,
        reminderIntervalHours: request.reminderConfig.intervalHours
      });

      try {
        await this._sendWithRetry({
          to: approval.email,
          subject,
          html,
          approvalRequestId: request._id,
          stakeholderName: approval.name,
          documentName: request.documentName,
          type: 'approval_request'
        });

        // Mark initial email sent on this stakeholder
        await ApprovalRequest.updateOne(
          { _id: request._id, 'approvals._id': approval._id },
          {
            $set: {
              'approvals.$.initialEmailSent': true,
              'approvals.$.initialEmailSentAt': new Date(),
              status: 'in_progress'
            }
          }
        );

        console.log(`[Email] ✅ Sent to stakeholder ${i + 1}: ${approval.email}`);
        results.push({ email: approval.email, success: true });
      } catch (err) {
        console.error(`[Email] ❌ Failed for stakeholder ${i + 1} (${approval.email}):`, err.message);
        results.push({ email: approval.email, success: false, error: err.message });
      }
    }

    const failed = results.filter(r => !r.success);
    if (failed.length > 0) {
      console.warn(`[Email] ${failed.length} email(s) failed:`, failed.map(f => f.email).join(', '));
    }

    return results;
  }

  // ── Process a stakeholder response (via token link) ──────────────────────

  /**
   * @param {string} token  - unique stakeholder token
   * @param {string} action - 'approve' | 'reject'
   * @param {string} comments
   * @returns updated ApprovalRequest
   */
  async processResponse(token, action, comments = '') {
    const request = await ApprovalRequest.findOne({ 'approvals.token': token });
    if (!request) throw new Error('Invalid or expired approval token');

    const approval = request.approvals.find(a => a.token === token);
    if (!approval) throw new Error('Token not found');
    if (approval.status !== 'pending') {
      throw new Error(`This approval has already been ${approval.status}`);
    }
    if (request.status === 'approved' || request.status === 'rejected') {
      throw new Error('This approval request has already been completed');
    }

    // Map action verb → status noun  ('approve' → 'approved', 'reject' → 'rejected')
    const statusMap = { approve: 'approved', reject: 'rejected' };
    approval.status = statusMap[action] || action;
    approval.respondedAt = new Date();
    approval.comments = comments;

    // Recount
    const approved = request.approvals.filter(a => a.status === 'approved').length;
    const rejected = request.approvals.filter(a => a.status === 'rejected').length;
    request.approvedCount = approved;
    request.rejectedCount = rejected;

    // Determine overall status
    let completed = false;
    if (rejected > 0) {
      request.status = 'rejected';
      request.completedAt = new Date();
      completed = true;
    } else if (approved >= request.requiredApprovals) {
      request.status = 'approved';
      request.completedAt = new Date();
      completed = true;
    }

    await request.save();

    // Sync document status
    if (completed) {
      await Document.findByIdAndUpdate(request.documentId, {
        status: request.status
      });

      // Notify submitter
      await this._notifyCompletion(request);
    }

    return request;
  }

  async _notifyCompletion(request) {
    if (!request.submittedByEmail) return;
    const cfg = await this._getConfig();
    const appUrl = cfg.appUrl || 'http://localhost:3000';

    const { subject, html } = completionTemplate({
      submittedBy: request.submittedBy,
      documentName: request.documentName,
      documentWebUrl: request.documentWebUrl,
      status: request.status,
      approvals: request.approvals,
      appUrl
    });

    try {
      await emailService.send({
        to: request.submittedByEmail,
        subject,
        html,
        approvalRequestId: request._id,
        stakeholderName: request.submittedBy,
        documentName: request.documentName,
        type: request.status === 'approved' ? 'all_approved' : 'rejected_notify'
      });
    } catch (err) {
      console.error('Failed to notify submitter:', err.message);
    }
  }

  // ── Get approval request by token (public — no auth) ─────────────────────

  async getByToken(token) {
    const request = await ApprovalRequest.findOne({ 'approvals.token': token })
      .populate('documentId');
    if (!request) throw new Error('Invalid token');
    const approval = request.approvals.find(a => a.token === token);
    return { request, approval };
  }

  // ── Manually trigger reminder for a request ───────────────────────────────

  async sendManualReminder(requestId) {
    const request = await ApprovalRequest.findById(requestId);
    if (!request) throw new Error('Approval request not found');

    const cfg = await this._getConfig();
    const appUrl = cfg.appUrl || 'http://localhost:3000';
    const { reminderTemplate } = require('../templates/emailTemplates');
    const sent = [];
    const pending = request.approvals.filter(a => a.status === 'pending');

    for (let i = 0; i < pending.length; i++) {
      const approval = pending[i];

      // Throttle gap between sends
      if (i > 0) await this._sleep(1500);

      const approveUrl = `${appUrl}/approve/${approval.token}?action=approve`;
      const rejectUrl  = `${appUrl}/approve/${approval.token}?action=reject`;

      const { subject, html } = reminderTemplate({
        stakeholderName: approval.name,
        documentName: request.documentName,
        documentWebUrl: request.documentWebUrl,
        approveUrl,
        rejectUrl,
        submittedBy: request.submittedBy,
        appUrl,
        reminderNumber: approval.reminderCount + 1,
        maxReminders: request.reminderConfig.maxReminders
      });

      try {
        await this._sendWithRetry({
          to: approval.email,
          subject,
          html,
          approvalRequestId: request._id,
          stakeholderName: approval.name,
          documentName: request.documentName,
          type: 'reminder'
        });

        approval.reminderCount += 1;
        approval.lastReminderSent = new Date();
        sent.push(approval.email);
        console.log(`[Reminder] ✅ Sent to ${approval.email}`);
      } catch (err) {
        console.error(`[Reminder] ❌ Failed for ${approval.email}:`, err.message);
      }
    }

    await request.save();
    return { sent };
  }
}

module.exports = new ApprovalService();
