require('dotenv').config();
const express = require('express');
const cors = require('cors');
const morgan = require('morgan');
const connectDB = require('./config/db');
const seedConfig = require('./config/seedConfig');
const schedulerService = require('./services/schedulerService');

const app = express();

// ── Database ────────────────────────────────────────────────────────────────
connectDB();

// ── Middleware ───────────────────────────────────────────────────────────────
// CLIENT_URL can be a comma-separated list, e.g.:
//   CLIENT_URL=https://my-app.vercel.app,https://my-app-git-main-xxx.vercel.app
const allowedOrigins = (process.env.CLIENT_URL || 'http://localhost:3000')
  .split(',').map(o => o.trim()).filter(Boolean);

app.use(cors({
  origin: (origin, cb) => {
    // Allow server-to-server / curl (no Origin header)
    if (!origin) return cb(null, true);
    // Exact match from allowlist
    if (allowedOrigins.includes(origin)) return cb(null, true);
    // Also allow any *.vercel.app subdomain (preview deployments)
    if (/^https:\/\/[\w-]+\.vercel\.app$/.test(origin)) return cb(null, true);
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

// Health check
app.get('/api/health', (req, res) => res.json({ status: 'ok', timestamp: new Date() }));

// ── Global error handler ─────────────────────────────────────────────────────
app.use((err, req, res, _next) => {
  console.error('[Error]', err.message);
  res.status(err.status || 500).json({ message: err.message || 'Internal server error' });
});

// ── Start ────────────────────────────────────────────────────────────────────
const PORT = process.env.PORT || 5000;
app.listen(PORT, async () => {
  console.log(`Server running on port ${PORT}`);
  await seedConfig();
  await schedulerService.init();
});

module.exports = app;
