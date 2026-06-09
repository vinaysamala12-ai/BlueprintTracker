const Config = require('../models/Config');
const emailService = require('../services/emailService');
const schedulerService = require('../services/schedulerService');
const asyncHandler = require('../middleware/asyncHandler');

// GET /api/config
exports.getConfig = asyncHandler(async (req, res) => {
  let cfg = await Config.findOne();
  if (!cfg) { cfg = new Config(); await cfg.save(); }

  const safe = cfg.toObject();
  if (safe.ms365?.clientSecret)   safe.ms365.clientSecret   = '••••••••';
  if (safe.storage?.clientSecret) safe.storage.clientSecret = '••••••••';

  res.json(safe);
});

// PUT /api/config
exports.updateConfig = asyncHandler(async (req, res) => {
  let cfg = await Config.findOne();
  if (!cfg) cfg = new Config();

  const { ms365, scheduler, storage, appUrl } = req.body;

  if (appUrl) cfg.appUrl = appUrl;

  if (ms365) {
    cfg.ms365.tenantId  = ms365.tenantId  ?? cfg.ms365.tenantId;
    cfg.ms365.clientId  = ms365.clientId  ?? cfg.ms365.clientId;
    cfg.ms365.fromEmail = ms365.fromEmail ?? cfg.ms365.fromEmail;
    cfg.ms365.fromName  = ms365.fromName  ?? cfg.ms365.fromName;
    if (ms365.clientSecret && ms365.clientSecret !== '••••••••') {
      cfg.ms365.clientSecret = ms365.clientSecret;
    }
  }

  if (scheduler) {
    const prevCron = cfg.scheduler.cronExpression;
    cfg.scheduler.enabled               = scheduler.enabled               ?? cfg.scheduler.enabled;
    cfg.scheduler.cronExpression        = scheduler.cronExpression        ?? cfg.scheduler.cronExpression;
    cfg.scheduler.reminderIntervalHours = scheduler.reminderIntervalHours ?? cfg.scheduler.reminderIntervalHours;
    cfg.scheduler.maxReminders          = scheduler.maxReminders          ?? cfg.scheduler.maxReminders;

    if (scheduler.cronExpression && scheduler.cronExpression !== prevCron) {
      cfg.scheduler.enabled ? schedulerService.restart(cfg.scheduler.cronExpression) : schedulerService.stop();
    }
    if (scheduler.enabled === false) schedulerService.stop();
    if (scheduler.enabled === true)  schedulerService.restart(cfg.scheduler.cronExpression);
  }

  if (storage) {
    cfg.storage.type       = storage.type       ?? cfg.storage.type;
    cfg.storage.tenantId   = storage.tenantId   ?? cfg.storage.tenantId;
    cfg.storage.clientId   = storage.clientId   ?? cfg.storage.clientId;
    cfg.storage.driveId    = storage.driveId    ?? cfg.storage.driveId;
    cfg.storage.siteUrl    = storage.siteUrl    ?? cfg.storage.siteUrl;
    cfg.storage.folderPath = storage.folderPath ?? cfg.storage.folderPath;
    if (storage.clientSecret && storage.clientSecret !== '••••••••') {
      cfg.storage.clientSecret = storage.clientSecret;
    }
  }

  await cfg.save();

  const safe = cfg.toObject();
  if (safe.ms365?.clientSecret)   safe.ms365.clientSecret   = '••••••••';
  if (safe.storage?.clientSecret) safe.storage.clientSecret = '••••••••';

  res.json({ message: 'Configuration saved', config: safe });
});

// POST /api/config/test-email
exports.testEmail = asyncHandler(async (req, res) => {
  const { toEmail } = req.body;
  if (!toEmail) return res.status(400).json({ message: 'toEmail is required' });
  const result = await emailService.testConnection(toEmail);
  res.json({ message: 'Test email sent successfully via Microsoft 365', ...result });
});
