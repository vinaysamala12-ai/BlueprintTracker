/**
 * schedulerService.js
 *
 * Runs a configurable cron job that:
 *  1. Finds all pending/in_progress approval requests
 *  2. For each pending stakeholder, checks if a reminder is due
 *  3. Sends reminder emails respecting maxReminders and intervalHours
 *
 * The cron expression and reminder settings are loaded from the DB Config
 * on every tick so that changes take effect without a server restart.
 */

const cron = require('node-cron');
const ApprovalRequest = require('../models/ApprovalRequest');
const Config = require('../models/Config');
const emailService = require('./emailService');
const { reminderTemplate } = require('../templates/emailTemplates');

class SchedulerService {
  constructor() {
    this._task = null;
    this._running = false;
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async _sendWithRetry(emailOpts, maxRetries = 3, baseDelayMs = 2000) {
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        return await emailService.send(emailOpts);
      } catch (err) {
        const status = err.response?.status || err.statusCode;
        const retryable = status === 429 || status === 503 || status === 502;
        if (retryable && attempt < maxRetries) {
          const retryAfter = err.response?.headers?.['retry-after'];
          const waitMs = retryAfter ? parseInt(retryAfter) * 1000 : baseDelayMs * attempt;
          console.warn(`[Scheduler] Rate-limited (${status}), retrying in ${waitMs}ms…`);
          await this._sleep(waitMs);
        } else {
          throw err;
        }
      }
    }
  }

  // ── Lifecycle ──────────────────────────────────────────────────────────────

  async init() {
    const cfg = await this._getConfig();
    if (!cfg.scheduler.enabled) {
      console.log('[Scheduler] Disabled via config.');
      return;
    }
    this._start(cfg.scheduler.cronExpression);
  }

  _start(cronExpression) {
    if (this._task) {
      this._task.stop();
    }
    console.log(`[Scheduler] Starting with cron: "${cronExpression}"`);
    this._task = cron.schedule(cronExpression, () => this._tick());
  }

  /** Restart the scheduler with a new cron expression (called after config update). */
  restart(cronExpression) {
    this._start(cronExpression);
  }

  stop() {
    if (this._task) {
      this._task.stop();
      this._task = null;
    }
  }

  // ── Tick ───────────────────────────────────────────────────────────────────

  async _tick() {
    if (this._running) return; // prevent overlapping runs
    this._running = true;
    console.log(`[Scheduler] Tick at ${new Date().toISOString()}`);

    try {
      const cfg = await this._getConfig();
      if (!cfg.scheduler.enabled) {
        this._running = false;
        return;
      }
      await this._processReminders(cfg);
    } catch (err) {
      console.error('[Scheduler] Error during tick:', err.message);
    } finally {
      this._running = false;
    }
  }

  async _processReminders(cfg) {
    const pendingRequests = await ApprovalRequest.find({
      status: { $in: ['pending', 'in_progress'] }
    });

    console.log(`[Scheduler] Checking ${pendingRequests.length} active request(s)...`);

    const appUrl = cfg.appUrl || 'http://localhost:3000';
    const {
      reminderIntervalHours,
      maxReminders
    } = cfg.scheduler;

    for (const request of pendingRequests) {
      // Use per-request config if set, fall back to global
      const intervalHours = request.reminderConfig?.intervalHours ?? reminderIntervalHours;
      const max = request.reminderConfig?.maxReminders ?? maxReminders;
      let dirty = false;

      for (const approval of request.approvals) {
        if (approval.status !== 'pending') continue;
        if (approval.reminderCount >= max) continue;

        const lastSent = approval.lastReminderSent || approval.initialEmailSentAt || request.createdAt;
        const hoursSinceLast = (Date.now() - new Date(lastSent).getTime()) / 3_600_000;

        if (hoursSinceLast < intervalHours) continue;

        const approveUrl = `${appUrl}/approve/${approval.token}?action=approve`;
        const rejectUrl = `${appUrl}/approve/${approval.token}?action=reject`;
        const { subject, html } = reminderTemplate({
          stakeholderName: approval.name,
          documentName: request.documentName,
          documentWebUrl: request.documentWebUrl,
          approveUrl,
          rejectUrl,
          submittedBy: request.submittedBy,
          appUrl,
          reminderNumber: approval.reminderCount + 1,
          maxReminders: max
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
          dirty = true;
          console.log(`[Scheduler] Reminder #${approval.reminderCount} sent to ${approval.email} for "${request.documentName}"`);
        } catch (err) {
          console.error(`[Scheduler] Failed reminder to ${approval.email}:`, err.message);
        }
      }

      if (dirty) await request.save();
    }
  }

  // ── Manual run (for testing / API trigger) ─────────────────────────────────

  async runNow() {
    const cfg = await this._getConfig();
    await this._processReminders(cfg);
    return { triggered: true, at: new Date().toISOString() };
  }

  async getStatus() {
    const cfg = await this._getConfig();
    return {
      enabled: cfg.scheduler.enabled,
      cronExpression: cfg.scheduler.cronExpression,
      reminderIntervalHours: cfg.scheduler.reminderIntervalHours,
      maxReminders: cfg.scheduler.maxReminders,
      isRunning: this._running,
      taskActive: !!this._task
    };
  }

  async _getConfig() {
    let cfg = await Config.findOne();
    if (!cfg) { cfg = new Config(); await cfg.save(); }
    return cfg;
  }
}

module.exports = new SchedulerService();
