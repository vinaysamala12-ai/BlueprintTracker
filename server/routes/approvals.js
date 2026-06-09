const router = require('express').Router();
const ctrl = require('../controllers/approvalController');

router.get('/stats', ctrl.getStats);
router.get('/logs/all', ctrl.getAllLogs);
router.get('/scheduler/status', ctrl.schedulerStatus);
router.post('/scheduler/run', ctrl.runScheduler);

router.get('/', ctrl.getApprovals);
router.get('/token/:token', ctrl.getByToken);
router.post('/respond/:token', ctrl.respond);

router.get('/:id', ctrl.getApproval);
router.get('/:id/logs', ctrl.getLogs);
router.post('/:id/remind', ctrl.sendReminder);

module.exports = router;
