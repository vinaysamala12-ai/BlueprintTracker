const router = require('express').Router();
const ctrl = require('../controllers/authController');
const { adminOnly } = require('../middleware/authMiddleware');

router.post('/login', ctrl.login);

// User management — admin only
router.get('/users',              adminOnly, ctrl.listUsers);
router.post('/users',             adminOnly, ctrl.createUser);
router.delete('/users/:username', adminOnly, ctrl.deleteUser);

module.exports = router;
