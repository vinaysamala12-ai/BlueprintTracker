const mongoose = require('mongoose');

const documentSchema = new mongoose.Schema({
  name: { type: String, required: true },
  path: { type: String, required: true },
  storageType: {
    type: String,
    enum: ['sharepoint', 'onedrive'],
    required: true
  },
  fileId: { type: String, default: '' },
  driveId: { type: String, default: '' },
  siteId: { type: String, default: '' },
  webUrl: { type: String, default: '' },
  mimeType: { type: String, default: '' },
  fileSize: { type: Number, default: 0 },
  status: {
    type: String,
    enum: ['pending', 'in_review', 'approved', 'rejected'],
    default: 'pending'
  },
  submittedBy: { type: String, required: true },
  submittedByEmail: { type: String, default: '' },
  approvalRequestId: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'ApprovalRequest',
    default: null
  }
}, { timestamps: true });

module.exports = mongoose.model('Document', documentSchema);
