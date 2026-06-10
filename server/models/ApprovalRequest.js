const mongoose = require('mongoose');

const stakeholderApprovalSchema = new mongoose.Schema({
  name: { type: String, required: true },
  email: { type: String, required: true },
  status: {
    type: String,
    enum: ['pending', 'approved', 'rejected'],
    default: 'pending'
  },
  token: { type: String, required: true },
  respondedAt: { type: Date, default: null },
  comments: { type: String, default: '' },
  reminderCount: { type: Number, default: 0 },
  lastReminderSent: { type: Date, default: null },
  initialEmailSent: { type: Boolean, default: false },
  initialEmailSentAt: { type: Date, default: null }
}, { _id: true });

const approvalRequestSchema = new mongoose.Schema({
  documentId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Document',
    required: true
  },
  documentName: { type: String, required: true },
  documentWebUrl: { type: String, default: '' },
  approvals: [stakeholderApprovalSchema],
  status: {
    type: String,
    enum: ['pending', 'in_progress', 'approved', 'rejected'],
    default: 'pending'
  },
  requiredApprovals: { type: Number, default: 3 },
  approvedCount: { type: Number, default: 0 },
  rejectedCount: { type: Number, default: 0 },
  completedAt: { type: Date, default: null },
  reminderConfig: {
    intervalHours: { type: Number, default: 24 },
    maxReminders: { type: Number, default: 3 }
  },
  submittedBy: { type: String, default: '' },
  submittedByEmail: { type: String, default: '' },
  notes: { type: String, default: '' },
  remindersEnabled: { type: Boolean, default: true }
}, { timestamps: true });

approvalRequestSchema.virtual('pendingCount').get(function () {
  return this.approvals.filter(a => a.status === 'pending').length;
});

approvalRequestSchema.set('toJSON', { virtuals: true });

module.exports = mongoose.model('ApprovalRequest', approvalRequestSchema);
