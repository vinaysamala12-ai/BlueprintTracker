const router = require('express').Router();
const ctrl = require('../controllers/configController');
const { adminOnly } = require('../middleware/authMiddleware');

router.get('/',             ctrl.getConfig);
router.put('/',             adminOnly, ctrl.updateConfig);
router.post('/test-email',  adminOnly, ctrl.testEmail);

module.exports = router;
