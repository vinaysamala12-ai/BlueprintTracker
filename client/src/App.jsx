import React from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import Dashboard from './components/Dashboard/Dashboard';
import DocumentList from './components/Documents/DocumentList';
import SubmitDocument from './components/Documents/SubmitDocument';
import ApprovalTracker from './components/ApprovalTracker/ApprovalTracker';
import Settings from './components/Settings/Settings';
import ApprovalPage from './components/Approve/ApprovalPage';
import NotificationLogs from './components/NotificationLogs/NotificationLogs';

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
  // Hide sidebar on the public approval page
  if (location.pathname.startsWith('/approve/')) return null;

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <h2>Document Approval</h2>
        <span>Workflow System</span>
      </div>
      <nav className="sidebar-nav">
        {NAV.map(n => (
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
    </aside>
  );
}

function Layout({ children }) {
  const location = useLocation();
  const isPublic = location.pathname.startsWith('/approve/');
  return isPublic ? children : (
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
          <Route path="/"           element={<Dashboard />} />
          <Route path="/documents"  element={<DocumentList />} />
          <Route path="/submit"     element={<SubmitDocument />} />
          <Route path="/approvals"  element={<ApprovalTracker />} />
          <Route path="/logs"       element={<NotificationLogs />} />
          <Route path="/settings"   element={<Settings />} />
          <Route path="/approve/:token" element={<ApprovalPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
