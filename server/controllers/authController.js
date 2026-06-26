const jwt  = require('jsonwebtoken');
const User = require('../models/User');

exports.login = async (req, res) => {
  const { username, password } = req.body;
  if (!process.env.JWT_SECRET) {
    return res.status(500).json({ message: 'Server auth not configured. Set JWT_SECRET env var.' });
  }

  const user = await User.findOne({ username: username?.toLowerCase() });
  if (!user || !(await user.comparePassword(password))) {
    return res.status(401).json({ message: 'Invalid username or password' });
  }

  const token = jwt.sign({ username: user.username, role: user.role }, process.env.JWT_SECRET, { expiresIn: '24h' });
  res.json({ token, username: user.username, role: user.role });
};

exports.listUsers = async (req, res) => {
  const users = await User.find({}, 'username role name email createdAt').lean();
  res.json({ users });
};

exports.createUser = async (req, res) => {
  const { username, password, name, email } = req.body;
  if (!username || !password) return res.status(400).json({ message: 'Username and password are required' });
  if (await User.findOne({ username: username.toLowerCase() })) {
    return res.status(409).json({ message: 'Username already exists' });
  }
  const user = await User.create({ username, password, role: 'user', name: name || '', email: email || '' });
  res.status(201).json({ user: { username: user.username, role: user.role, name: user.name, email: user.email } });
};

exports.deleteUser = async (req, res) => {
  const { username } = req.params;
  if (username === req.user.username) return res.status(400).json({ message: 'Cannot delete your own account' });
  const result = await User.deleteOne({ username, role: 'user' });
  if (result.deletedCount === 0) return res.status(404).json({ message: 'User not found or cannot delete admin' });
  res.json({ message: 'User deleted' });
};
