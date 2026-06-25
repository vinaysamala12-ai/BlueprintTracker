const Document = require('../models/Document');
const ApprovalRequest = require('../models/ApprovalRequest');
const approvalService = require('../services/approvalService');
const asyncHandler = require('../middleware/asyncHandler');

// GET /api/documents
exports.getDocuments = asyncHandler(async (req, res) => {
  const { status, search, page = 1, limit = 20 } = req.query;
  const query = {};
  if (status) query.status = status;
  if (search) query.name = { $regex: search, $options: 'i' };

  const skip = (parseInt(page) - 1) * parseInt(limit);
  const [docs, total] = await Promise.all([
    Document.find(query)
      .populate('approvalRequestId')
      .sort({ createdAt: -1 })
      .skip(skip)
      .limit(parseInt(limit)),
    Document.countDocuments(query)
  ]);

  res.json({ documents: docs, total, page: parseInt(page), pages: Math.ceil(total / limit) });
});

// GET /api/documents/:id
exports.getDocument = asyncHandler(async (req, res) => {
  const doc = await Document.findById(req.params.id).populate('approvalRequestId');
  if (!doc) return res.status(404).json({ message: 'Document not found' });
  res.json(doc);
});

// POST /api/documents/submit
exports.submitDocument = asyncHandler(async (req, res) => {
  const {
    name, path, storageType, fileId, driveId, siteId, webUrl,
    mimeType, fileSize, submittedBy, submittedByEmail,
    stakeholders, notes, reminderConfig
  } = req.body;

  if (!stakeholders || stakeholders.length < 1) {
    return res.status(400).json({ message: 'At least one stakeholder is required' });
  }

  // Create the document record
  const doc = await Document.create({
    name, path, storageType, fileId, driveId, siteId,
    webUrl: webUrl || '', mimeType: mimeType || '',
    fileSize: fileSize || 0, submittedBy, submittedByEmail,
    status: 'pending'
  });

  // Create approval request and send emails
  const approvalRequest = await approvalService.createApprovalRequest({
    documentId: doc._id,
    stakeholders,
    submittedBy,
    submittedByEmail,
    notes,
    reminderConfig
  });

  res.status(201).json({ document: doc, approvalRequest });
});

// DELETE /api/documents/:id
exports.deleteDocument = asyncHandler(async (req, res) => {
  const doc = await Document.findById(req.params.id);
  if (!doc) return res.status(404).json({ message: 'Document not found' });

  if (doc.approvalRequestId) {
    await ApprovalRequest.findByIdAndDelete(doc.approvalRequestId);
  }
  await doc.deleteOne();

  res.json({ message: 'Document deleted' });
});

// GET /api/documents/stats
exports.getStats = asyncHandler(async (req, res) => {
  const [total, pending, in_review, approved, rejected] = await Promise.all([
    Document.countDocuments(),
    Document.countDocuments({ status: 'pending' }),
    Document.countDocuments({ status: 'in_review' }),
    Document.countDocuments({ status: 'approved' }),
    Document.countDocuments({ status: 'rejected' })
  ]);
  res.json({ total, pending, in_review, approved, rejected });
});
