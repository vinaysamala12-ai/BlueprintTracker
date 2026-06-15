const jwt = require('jsonwebtoken');

// Paths that never require a token — stakeholder approval flow + cron trigger
const PUBLIC_PATHS = [
  { method: 'POST', path: '/api/auth/login' },
  { method: 'GET',  path: '/api/health' },
  { method: 'GET',  path: '/api/approvals/token/' },        // approval page load
  { method: 'POST', path: '/api/approvals/respond/' },      // approve / reject submit
  { method: 'POST', path: '/api/approvals/scheduler/run' }, // cron-job.org
  { method: 'GET',  path: '/api/approvals/scheduler/run' }, // browser test
];

module.exports = (req, res, next) => {
  const isPublic = PUBLIC_PATHS.some(p =>
    req.method === p.method && req.path.startsWith(p.path)
  );
  if (isPublic) return next();

  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ message: 'Authentication required' });

  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET || 'dev-secret-change-me');
    next();
  } catch {
    res.status(401).json({ message: 'Invalid or expired token — please log in again' });
  }
};
