const ApprovalRequest = require('../models/ApprovalRequest');
const NotificationLog = require('../models/NotificationLog');
const approvalService = require('../services/approvalService');
const schedulerService = require('../services/schedulerService');
const asyncHandler = require('../middleware/asyncHandler');

// GET /api/approvals
exports.getApprovals = asyncHandler(async (req, res) => {
  const { status, search, page = 1, limit = 20 } = req.query;
  const query = {};
  if (status) query.status = status;
  if (search) query.documentName = { $regex: search, $options: 'i' };

  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [requests, total] = await Promise.all([
    ApprovalRequest.find(query)
      .populate('documentId')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit)),
    ApprovalRequest.countDocuments(query)
  ]);

  res.json({ requests, total, page: parseInt(page), pages: Math.ceil(total / limit) });
});

// GET /api/approvals/stats
exports.getStats = asyncHandler(async (req, res) => {
  const [total, pending, in_progress, approved, rejected] = await Promise.all([
    ApprovalRequest.countDocuments(),
    ApprovalRequest.countDocuments({ status: 'pending' }),
    ApprovalRequest.countDocuments({ status: 'in_progress' }),
    ApprovalRequest.countDocuments({ status: 'approved' }),
    ApprovalRequest.countDocuments({ status: 'rejected' })
  ]);

  // Total reminders sent
  const reminderCount = await NotificationLog.countDocuments({ type: 'reminder' });

  res.json({ total, pending, in_progress, approved, rejected, reminderCount });
});

// GET /api/approvals/:id
exports.getApproval = asyncHandler(async (req, res) => {
  const request = await ApprovalRequest.findById(req.params.id).populate('documentId');
  if (!request) return res.status(404).json({ message: 'Approval request not found' });
  res.json(request);
});

// GET /api/approvals/token/:token  — public, used by the email link page
exports.getByToken = asyncHandler(async (req, res) => {
  const { request, approval } = await approvalService.getByToken(req.params.token);
  res.json({
    documentName: request.documentName,
    documentWebUrl: request.documentWebUrl,
    stakeholderName: approval.name,
    stakeholderEmail: approval.email,
    status: approval.status,
    requestStatus: request.status,
    submittedBy: request.submittedBy,
    createdAt: request.createdAt
  });
});

// POST /api/approvals/respond/:token  — public
exports.respond = asyncHandler(async (req, res) => {
  const { action, comments } = req.body;
  if (!['approve', 'reject', 'changes_made'].includes(action)) {
    return res.status(400).json({ message: 'Action must be "approve", "reject", or "changes_made"' });
  }
  const request = await approvalService.processResponse(req.params.token, action, comments);
  const message = action === 'changes_made'
    ? 'Document update noted — all stakeholders will receive new review emails'
    : `Document ${action}d successfully`;
  res.json({
    message,
    status: request.status,
    approvedCount: request.approvedCount,
    rejectedCount: request.rejectedCount
  });
});

// POST /api/approvals/:id/remind  — manual reminder
exports.sendReminder = asyncHandler(async (req, res) => {
  const result = await approvalService.sendManualReminder(req.params.id);
  res.json({ message: 'Reminders sent', sent: result.sent });
});

// PATCH /api/approvals/:id/reminders  — enable or disable reminders for one request
exports.toggleReminders = asyncHandler(async (req, res) => {
  const request = await ApprovalRequest.findById(req.params.id);
  if (!request) return res.status(404).json({ message: 'Approval request not found' });
  request.remindersEnabled = req.body.enabled !== false; // default true if not provided
  await request.save();
  res.json({
    message: request.remindersEnabled ? 'Reminders resumed' : 'Reminders stopped',
    remindersEnabled: request.remindersEnabled
  });
});

// POST /api/approvals/scheduler/run  — manual trigger / Vercel Cron
exports.runScheduler = asyncHandler(async (req, res) => {
  console.log(`[Cron] Triggered at ${new Date().toISOString()} by ${req.headers['x-vercel-cron'] ? 'Vercel Cron' : 'manual call'}`);
  const result = await schedulerService.runNow();
  console.log(`[Cron] Completed:`, JSON.stringify(result));
  res.json(result);
});

// GET /api/approvals/scheduler/status
exports.schedulerStatus = asyncHandler(async (req, res) => {
  const status = await schedulerService.getStatus();
  res.json(status);
});

// GET /api/approvals/:id/logs  — notification log for one request
exports.getLogs = asyncHandler(async (req, res) => {
  const logs = await NotificationLog.find({ approvalRequestId: req.params.id })
    .sort({ sentAt: -1 });
  res.json(logs);
});

// GET /api/approvals/logs/all
exports.getAllLogs = asyncHandler(async (req, res) => {
  const { page = 1, limit = 50 } = req.query;
  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [logs, total] = await Promise.all([
    NotificationLog.find().sort({ sentAt: -1 }).skip(skip).limit(parseInt(limit)),
    NotificationLog.countDocuments()
  ]);
  res.json({ logs, total });
});
