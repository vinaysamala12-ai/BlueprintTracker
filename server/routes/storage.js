const router = require('express').Router();
const ctrl = require('../controllers/storageController');

router.get('/files', ctrl.listFiles);
router.get('/file/:driveId/:fileId', ctrl.getFile);
router.post('/test', ctrl.testConnection);
router.post('/upload', ctrl.uploadMiddleware, ctrl.uploadFile);

module.exports = router;
