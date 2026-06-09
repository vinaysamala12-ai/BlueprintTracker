/**
 * seedConfig.js
 * On startup, populate the Config document from environment variables
 * so .env values are respected without manual Settings-page entry.
 */

const Config = require('../models/Config');

const seedConfig = async () => {
  try {
    let cfg = await Config.findOne();
    if (!cfg) cfg = new Config();

    // ── Microsoft 365 email ───────────────────────────────────────────────
    if (process.env.MS365_TENANT_ID &&
        (!cfg.ms365.tenantId || cfg.ms365.tenantId !== process.env.MS365_TENANT_ID)) {
      cfg.ms365.tenantId     = process.env.MS365_TENANT_ID;
      cfg.ms365.clientId     = process.env.MS365_CLIENT_ID     || '';
      cfg.ms365.clientSecret = process.env.MS365_CLIENT_SECRET || '';
      cfg.ms365.fromEmail    = process.env.MS365_FROM_EMAIL    || '';
      cfg.ms365.fromName     = process.env.MS365_FROM_NAME     || 'Document Approval System';
      console.log('[Config] MS365 email settings loaded from .env');
    }

    // ── Storage — SharePoint / OneDrive ───────────────────────────────────
    const isPlaceholder = (v) => !v || v.startsWith('your-');
    const graphTenant = isPlaceholder(process.env.GRAPH_TENANT_ID)
      ? process.env.MS365_TENANT_ID
      : process.env.GRAPH_TENANT_ID;
    const graphClient = isPlaceholder(process.env.GRAPH_CLIENT_ID)
      ? process.env.MS365_CLIENT_ID
      : process.env.GRAPH_CLIENT_ID;
    const graphSecret = isPlaceholder(process.env.GRAPH_CLIENT_SECRET)
      ? process.env.MS365_CLIENT_SECRET
      : process.env.GRAPH_CLIENT_SECRET;

    if (graphTenant && !isPlaceholder(graphTenant) &&
        (!cfg.storage.tenantId || cfg.storage.tenantId !== graphTenant)) {
      cfg.storage.tenantId     = graphTenant;
      cfg.storage.clientId     = graphClient || '';
      cfg.storage.clientSecret = graphSecret || '';

      if (process.env.SHAREPOINT_SITE_URL) {
        cfg.storage.type       = 'sharepoint';
        cfg.storage.siteUrl    = process.env.SHAREPOINT_SITE_URL;
        cfg.storage.folderPath = process.env.SHAREPOINT_LIBRARY || 'Documents';
      } else {
        cfg.storage.type    = 'onedrive';
        cfg.storage.driveId = process.env.ONEDRIVE_DRIVE_ID || '';
      }
      console.log(`[Config] Storage (${cfg.storage.type}) settings loaded from .env`);
    }

    // ── Scheduler ─────────────────────────────────────────────────────────
    if (process.env.SCHEDULER_CRON &&
        cfg.scheduler.cronExpression === '0 * * * *') {
      cfg.scheduler.cronExpression      = process.env.SCHEDULER_CRON;
      cfg.scheduler.reminderIntervalHours = parseInt(process.env.REMINDER_INTERVAL_HOURS) || 24;
      cfg.scheduler.maxReminders          = parseInt(process.env.MAX_REMINDERS)           || 3;
    }

    // ── App URL ───────────────────────────────────────────────────────────
    if (process.env.APP_URL) cfg.appUrl = process.env.APP_URL;

    await cfg.save();
    console.log('[Config] Configuration ready.');
  } catch (err) {
    console.error('[Config] Failed to seed config:', err.message);
  }
};

module.exports = seedConfig;
