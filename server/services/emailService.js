/**
 * emailService.js
 *
 * Sends emails exclusively via Microsoft 365 (Microsoft Graph API).
 * Uses OAuth2 client-credentials flow — no user login required.
 *
 * Azure AD App Registration requirements:
 *   • Mail.Send  (Application permission, admin-consented)
 */

const axios = require('axios');
const Config = require('../models/Config');
const NotificationLog = require('../models/NotificationLog');

class EmailService {
  // ── helpers ────────────────────────────────────────────────────────────────

  async _getConfig() {
    let cfg = await Config.findOne();
    if (!cfg) { cfg = new Config(); await cfg.save(); }
    return cfg;
  }

  async _getToken(cfg) {
    const { tenantId, clientId, clientSecret } = cfg.ms365;
    if (!tenantId || !clientId || !clientSecret) {
      throw new Error('MS365 credentials not configured. Set Tenant ID, Client ID and Client Secret in Settings → Email.');
    }
    const url = `https://login.microsoftonline.com/${tenantId}/oauth2/v2.0/token`;
    const params = new URLSearchParams({
      client_id:     clientId,
      client_secret: clientSecret,
      scope:         'https://graph.microsoft.com/.default',
      grant_type:    'client_credentials'
    });
    const res = await axios.post(url, params.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    });
    return res.data.access_token;
  }

  // ── public API ─────────────────────────────────────────────────────────────

  /**
   * Send an email via Microsoft 365 Graph API.
   * Automatically logs the result to NotificationLog.
   */
  async send({ to, subject, html, approvalRequestId = null, stakeholderName = '', documentName = '', type }) {
    const cfg = await this._getConfig();

    try {
      await this._sendMS365(cfg, { to, subject, html });

      await NotificationLog.create({
        approvalRequestId,
        documentName,
        stakeholderEmail:  to,
        stakeholderName,
        type,
        emailProvider: 'ms365',
        subject,
        status: 'sent'
      });

      return { success: true, provider: 'ms365' };
    } catch (err) {
      await NotificationLog.create({
        approvalRequestId,
        documentName,
        stakeholderEmail:  to,
        stakeholderName,
        type,
        emailProvider: 'ms365',
        subject,
        status: 'failed',
        errorMessage: err.message
      });
      throw err;
    }
  }

  /** Send a test email and verify the connection. */
  async testConnection(toEmail) {
    const cfg = await this._getConfig();

    // Step 1 — verify token
    let token;
    try {
      token = await this._getToken(cfg);
    } catch (err) {
      const detail = err.response?.data?.error_description || err.message;
      throw new Error(`MS365 authentication failed: ${detail}`);
    }

    // Step 2 — send test email
    if (toEmail) {
      const { testEmailTemplate } = require('../templates/emailTemplates');
      const { subject, html } = testEmailTemplate({ provider: 'ms365' });
      try {
        await this._callSendMail(cfg, token, { to: toEmail, subject, html });
      } catch (err) {
        const status = err.response?.status;
        const code   = err.response?.data?.error?.code;
        const detail = err.response?.data?.error?.message || err.message;
        if (status === 403) {
          throw new Error(
            `Access denied (403). Ensure the Azure App has Mail.Send (Application) permission with Admin Consent.\n` +
            `Graph error: ${code} — ${detail}`
          );
        }
        throw new Error(`Send failed (${status}): ${detail}`);
      }
    }

    return { success: true, provider: 'ms365' };
  }

  // ── internal ───────────────────────────────────────────────────────────────

  async _sendMS365(cfg, { to, subject, html }) {
    const token = await this._getToken(cfg);
    await this._callSendMail(cfg, token, { to, subject, html });
  }

  async _callSendMail(cfg, token, { to, subject, html }) {
    await axios.post(
      `https://graph.microsoft.com/v1.0/users/${cfg.ms365.fromEmail}/sendMail`,
      {
        message: {
          subject,
          body:           { contentType: 'HTML', content: html },
          toRecipients:   [{ emailAddress: { address: to } }],
          from:           { emailAddress: { name: cfg.ms365.fromName, address: cfg.ms365.fromEmail } }
        },
        saveToSentItems: true
      },
      {
        headers: {
          Authorization:  `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      }
    );
  }
}

module.exports = new EmailService();
