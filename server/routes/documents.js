const router = require('express').Router();
const ctrl = require('../controllers/documentController');

router.get('/stats', ctrl.getStats);
router.get('/', ctrl.getDocuments);
router.get('/:id', ctrl.getDocument);
router.post('/submit', ctrl.submitDocument);
router.delete('/:id', ctrl.deleteDocument);

module.exports = router;
