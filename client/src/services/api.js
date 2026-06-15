import axios from 'axios';

// In production REACT_APP_API_URL points at the Railway backend (e.g. https://xxx.railway.app/api).
// In dev the CRA proxy (package.json → "proxy") forwards /api → localhost:5000.
const api = axios.create({ baseURL: process.env.REACT_APP_API_URL || '/api' });

// Attach JWT token to every request
api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('auth_token');
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

// On 401 outside the public approval page — clear token and redirect to login
api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401 && !window.location.pathname.startsWith('/approve/')) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    const message = err.response?.data?.message || err.message || 'Request failed';
    return Promise.reject(new Error(message));
  }
);

// ── Auth ─────────────────────────────────────────────────────────────────────
export const login = (username, password) => api.post('/auth/login', { username, password });

// ── Documents ────────────────────────────────────────────────────────────────
export const getDocuments = (params) => api.get('/documents', { params });
export const getDocument = (id) => api.get(`/documents/${id}`);
export const submitDocument = (data) => api.post('/documents/submit', data);
export const deleteDocument = (id) => api.delete(`/documents/${id}`);
export const getDocumentStats = () => api.get('/documents/stats');

// ── Approvals ────────────────────────────────────────────────────────────────
export const getApprovals = (params) => api.get('/approvals', { params });
export const getApproval = (id) => api.get(`/approvals/${id}`);
export const getApprovalStats = () => api.get('/approvals/stats');
export const getApprovalByToken = (token) => api.get(`/approvals/token/${token}`);
export const respondToApproval = (token, data) => api.post(`/approvals/respond/${token}`, data);
export const sendReminder = (id) => api.post(`/approvals/${id}/remind`);
export const toggleReminders = (id, enabled) => api.patch(`/approvals/${id}/reminders`, { enabled });
export const getApprovalLogs = (id) => api.get(`/approvals/${id}/logs`);
export const getAllLogs = (params) => api.get('/approvals/logs/all', { params });
export const getSchedulerStatus = () => api.get('/approvals/scheduler/status');
export const runSchedulerNow = () => api.post('/approvals/scheduler/run');

// ── Config ───────────────────────────────────────────────────────────────────
export const getConfig = () => api.get('/config');
export const updateConfig = (data) => api.put('/config', data);
export const testEmail = (toEmail) => api.post('/config/test-email', { toEmail });

// ── Storage ──────────────────────────────────────────────────────────────────
export const listFiles = (folder) => api.get('/storage/files', { params: { folder } });
export const testStorage = () => api.post('/storage/test');
export const uploadFile = (formData, onProgress) =>
  api.post('/storage/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round((e.loaded * 100) / e.total))
  });
