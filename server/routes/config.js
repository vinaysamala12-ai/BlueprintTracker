const router = require('express').Router();
const ctrl = require('../controllers/configController');

router.get('/', ctrl.getConfig);
router.put('/', ctrl.updateConfig);
router.post('/test-email', ctrl.testEmail);

module.exports = router;
