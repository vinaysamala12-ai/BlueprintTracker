const multer = require('multer');
const storageService = require('../services/storageService');
const asyncHandler = require('../middleware/asyncHandler');

// Keep file in memory (no temp disk writes)
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 250 * 1024 * 1024 } // 250 MB max
});

exports.uploadMiddleware = upload.single('file');

// GET /api/storage/files?folder=/path
exports.listFiles = asyncHandler(async (req, res) => {
  const { folder } = req.query;
  const files = await storageService.listFiles(folder);
  res.json({ files });
});

// GET /api/storage/file/:driveId/:fileId
exports.getFile = asyncHandler(async (req, res) => {
  const { driveId, fileId } = req.params;
  const file = await storageService.getFile(driveId, fileId);
  res.json(file);
});

// POST /api/storage/test
exports.testConnection = asyncHandler(async (req, res) => {
  const result = await storageService.testConnection();
  res.json(result);
});

// POST /api/storage/upload  (multipart/form-data, field: "file", optional: "folder")
exports.uploadFile = asyncHandler(async (req, res) => {
  if (!req.file) return res.status(400).json({ message: 'No file provided' });

  const { originalname, buffer, mimetype } = req.file;
  const folder = req.body.folder || undefined;

  const result = await storageService.uploadFile(buffer, originalname, mimetype, folder);
  res.status(201).json({ message: 'File uploaded successfully', file: result });
});
