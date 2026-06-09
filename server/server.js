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
app.use(cors({ origin: process.env.CLIENT_URL || 'http://localhost:3000' }));
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
