import React from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom';
import Dashboard from './components/Dashboard/Dashboard';
import DocumentList from './components/Documents/DocumentList';
import SubmitDocument from './components/Documents/SubmitDocument';
import ApprovalTracker from './components/ApprovalTracker/ApprovalTracker';
import Settings from './components/Settings/Settings';
import ApprovalPage from './components/Approve/ApprovalPage';
import NotificationLogs from './components/NotificationLogs/NotificationLogs';
import Login from './components/Login/Login';
import ProtectedRoute from './components/ProtectedRoute';
import { Navigate } from 'react-router-dom';

const NAV = [
  { to: '/',           label: 'Dashboard',       icon: '🏠' },
  { to: '/documents',  label: 'Documents',        icon: '📄' },
  { to: '/submit',     label: 'Submit Document',  icon: '⬆️'  },
  { to: '/approvals',  label: 'Approval Tracker', icon: '✅' },
  { to: '/logs',       label: 'Notification Logs',icon: '📋' },
  { to: '/settings',   label: 'Settings',         icon: '⚙️'  },
];

function Sidebar() {
  const location = useLocation();
  const nav = useNavigate();
  const isAdmin = localStorage.getItem('auth_role') === 'admin';

  // Hide sidebar on the public approval page and login page
  if (location.pathname.startsWith('/approve/') || location.pathname === '/login') return null;

  function handleLogout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('auth_role');
    nav('/login', { replace: true });
  }

  const visibleNav = NAV.filter(n => n.to !== '/settings' || isAdmin);

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h2>Document Approval</h2>
        <span>Workflow System</span>
      </div>
      <nav className="sidebar-nav">
        {visibleNav.map(n => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === '/'}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            <span className="nav-icon">{n.icon}</span>
            {n.label}
          </NavLink>
        ))}
      </nav>
      <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.08)', marginTop: 'auto' }}>
        <button
          onClick={handleLogout}
          style={{
            width: '100%', padding: '10px 14px', background: 'rgba(255,255,255,0.06)',
            border: '1px solid rgba(255,255,255,0.12)', borderRadius: 8,
            color: '#94a3b8', fontSize: 13, cursor: 'pointer', textAlign: 'left',
            display: 'flex', alignItems: 'center', gap: 8, transition: 'all 0.15s'
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.12)'}
          onMouseLeave={e => e.currentTarget.style.background = 'rgba(255,255,255,0.06)'}
        >
          🚪 Logout
        </button>
      </div>
    </aside>
  );
}

function Layout({ children }) {
  const location = useLocation();
  const isFullPage = location.pathname.startsWith('/approve/') || location.pathname === '/login';
  return isFullPage ? children : (
    <div className="app">
      <Sidebar />
      <main className="main-content">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          {/* Public routes — no auth required */}
          <Route path="/login"          element={<Login />} />
          <Route path="/approve/:token" element={<ApprovalPage />} />

          {/* Protected routes — redirect to /login if not authenticated */}
          <Route path="/"          element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/documents" element={<ProtectedRoute><DocumentList /></ProtectedRoute>} />
          <Route path="/submit"    element={<ProtectedRoute><SubmitDocument /></ProtectedRoute>} />
          <Route path="/approvals" element={<ProtectedRoute><ApprovalTracker /></ProtectedRoute>} />
          <Route path="/logs"      element={<ProtectedRoute><NotificationLogs /></ProtectedRoute>} />
          <Route path="/settings"  element={<ProtectedRoute>{localStorage.getItem('auth_role') === 'admin' ? <Settings /> : <Navigate to="/" replace />}</ProtectedRoute>} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
