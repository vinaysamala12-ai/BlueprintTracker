const mongoose = require('mongoose');

const notificationLogSchema = new mongoose.Schema({
  approvalRequestId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'ApprovalRequest',
    default: null
  },
  documentName: { type: String, default: '' },
  stakeholderEmail: { type: String, required: true },
  stakeholderName: { type: String, default: '' },
  type: {
    type: String,
    enum: ['approval_request', 'reminder', 'approved_notify', 'rejected_notify', 'all_approved', 'test'],
    required: true
  },
  emailProvider: {
    type: String,
    enum: ['smtp', 'ms365'],
    required: true
  },
  subject: { type: String, default: '' },
  status: {
    type: String,
    enum: ['sent', 'failed'],
    default: 'sent'
  },
  errorMessage: { type: String, default: '' },
  sentAt: { type: Date, default: Date.now }
}, { timestamps: true });

module.exports = mongoose.model('NotificationLog', notificationLogSchema);
