const jwt = require('jsonwebtoken');

exports.login = (req, res) => {
  const { username, password } = req.body;

  const validUser = process.env.ADMIN_USERNAME || 'admin';
  const validPass = process.env.ADMIN_PASSWORD;

  if (!validPass) {
    console.error('[Auth] ADMIN_PASSWORD env var is not set');
    return res.status(500).json({ message: 'Server auth not configured. Set ADMIN_PASSWORD env var.' });
  }

  if (username !== validUser || password !== validPass) {
    return res.status(401).json({ message: 'Invalid username or password' });
  }

  if (!process.env.JWT_SECRET) {
    console.error('[Auth] JWT_SECRET env var is not set');
    return res.status(500).json({ message: 'Server auth not configured. Set JWT_SECRET env var.' });
  }

  const token = jwt.sign({ username }, process.env.JWT_SECRET, { expiresIn: '24h' });

  res.json({ token, username });
};
