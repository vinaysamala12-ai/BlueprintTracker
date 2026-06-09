require('dotenv').config();
const express = require('express');
const cors = require('cors');
const morgan = require('morgan');
const connectDB = require('./config/db');
const seedConfig = require('./config/seedConfig');
const schedulerService = require('./services/schedulerService');

// On Vercel, VERCEL=1 is set automatically by the platform
const IS_SERVERLESS = process.env.VERCEL === '1';

const app = express();

// ── Database + seed ──────────────────────────────────────────────────────────
// Run at module load time (executes on every cold start on Vercel).
// seedConfig must wait for the DB connection — await them in sequence.
(async () => {
  await connectDB();
  await seedConfig().catch(err => console.error('[seedConfig]', err.message));
})();

// ── Middleware ────────────────────────────────────────────────────────────────
// CLIENT_URL can be comma-separated, e.g.:
//   CLIENT_URL=https://my-app.vercel.app,https://my-app-git-main.vercel.app
const allowedOrigins = (process.env.CLIENT_URL || 'http://localhost:3000')
  .split(',').map(o => o.trim()).filter(Boolean);

app.use(cors({
  origin: (origin, cb) => {
    if (!origin) return cb(null, true);                                   // server-to-server / curl
    if (allowedOrigins.includes(origin)) return cb(null, true);          // exact match
    if (/^https:\/\/[\w-]+\.vercel\.app$/.test(origin)) return cb(null, true); // any *.vercel.app preview
    cb(new Error(`CORS: origin ${origin} not allowed`));
  },
  credentials: true
}));
app.use(express.json());
app.use(morgan('dev'));

// ── Routes ───────────────────────────────────────────────────────────────────
app.use('/api/documents', require('./routes/documents'));
app.use('/api/approvals', require('./routes/approvals'));
app.use('/api/config', require('./routes/config'));
app.use('/api/storage', require('./routes/storage'));

app.get('/api/health', (_req, res) => res.json({ status: 'ok', timestamp: new Date() }));

// ── Global error handler ──────────────────────────────────────────────────────
app.use((err, _req, res, _next) => {
  console.error('[Error]', err.message);
  res.status(err.status || 500).json({ message: err.message || 'Internal server error' });
});

// ── Scheduler + HTTP server (persistent mode only) ────────────────────────────
// On Vercel these are skipped — Vercel handles HTTP and its built-in Cron Jobs
// call POST /api/approvals/scheduler/run on the configured schedule.
if (!IS_SERVERLESS) {
  schedulerService.init()
    .then(() => console.log('[Scheduler] node-cron initialised'))
    .catch(err => console.error('[Scheduler]', err.message));

  const PORT = process.env.PORT || 5000;
  app.listen(PORT, () => console.log(`Server running on port ${PORT}`));
}

// Vercel needs the Express app exported as the default handler
module.exports = app;
