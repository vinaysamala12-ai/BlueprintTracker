# Document Approval Workflow — MERN

A full-stack MERN application for managing a **3-stakeholder document approval workflow** with:

- 📧 Email notifications via **SMTP** or **Microsoft 365 (Graph API)**
- ☁️ Document browsing from **SharePoint** or **OneDrive** (via Graph API)
- ⏰ **Configurable scheduler** — cron-based, DB-driven, live-restartable
- 📋 **Approval tracker** with timeline, progress bars, and notification logs
- 🔗 **Token-based approval links** in emails (no login required for stakeholders)

---

## Architecture

```
approval-workflow/
├── server/                  # Express + MongoDB backend
│   ├── models/              # Mongoose schemas
│   │   ├── Config.js        # All app settings (email, scheduler, storage)
│   │   ├── Document.js      # Document records
│   │   ├── ApprovalRequest.js  # Approval workflow with per-stakeholder tokens
│   │   └── NotificationLog.js  # Every email sent/failed
│   ├── services/
│   │   ├── emailService.js  # SMTP + MS365 Graph API
│   │   ├── approvalService.js  # Create/process approvals, send emails
│   │   ├── schedulerService.js # node-cron, DB-configurable, live-restart
│   │   └── storageService.js   # SharePoint + OneDrive via Graph API
│   ├── controllers/         # Route handlers
│   ├── routes/              # Express routers
│   └── templates/
│       └── emailTemplates.js  # HTML email templates (request, reminder, completion)
└── client/                  # React frontend
    └── src/components/
        ├── Dashboard/       # Stats overview + scheduler status
        ├── Documents/       # Document list + submit form
        ├── ApprovalTracker/ # Master-detail tracker with timeline
        ├── Settings/        # Email/scheduler/storage config UI
        ├── Approve/         # Public token-based approval page
        └── NotificationLogs/# Full email audit log
```

---

## Quick Start

### Prerequisites
- Node.js 18+
- MongoDB (local or Atlas)

### 1. Install dependencies

```bash
cd approval-workflow
npm install          # root (concurrently)
cd server && npm install
cd ../client && npm install
```

### 2. Configure environment

```bash
cp server/.env.example server/.env
# Edit server/.env with your MongoDB URI, email settings, etc.
```

### 3. Run

```bash
# From the root directory — runs both server (port 5000) and client (port 3000)
npm run dev
```

---

## Email: SMTP vs Microsoft 365

### Option A — SMTP
Works with any SMTP provider (Gmail, Outlook, SendGrid, Mailgun, custom relay).

**Gmail example:**
1. Enable 2FA on your Google account
2. Create an **App Password**: Google Account → Security → App Passwords
3. Set `SMTP_HOST=smtp.gmail.com`, port `587`, `SMTP_USER=you@gmail.com`, `SMTP_PASS=your-app-password`

**Settings UI** (Settings → Email → SMTP):
| Field | Example |
|-------|---------|
| Host | `smtp.gmail.com` |
| Port | `587` |
| SSL  | false (use STARTTLS) |
| User | `you@gmail.com` |
| Password | App password |
| From Email | `no-reply@yourcompany.com` |

### Option B — Microsoft 365 (Graph API)
Uses the **Microsoft Graph API `sendMail` endpoint** with an Azure AD service principal.

**Setup:**
1. Go to [Azure Portal](https://portal.azure.com) → Azure Active Directory → App registrations → New registration
2. Note the **Tenant ID**, **Client ID**
3. Certificates & secrets → New client secret → copy the **Value**
4. API permissions → Add → Microsoft Graph → Application permissions → add `Mail.Send`
5. Grant admin consent

**Settings UI** (Settings → Email → Microsoft 365):
| Field | Value |
|-------|-------|
| Tenant ID | From Azure AD |
| Client ID | App registration Application (client) ID |
| Client Secret | Secret value (not the ID) |
| From Email | Licensed M365 mailbox, e.g. `no-reply@yourcompany.com` |

> **Note:** The from address must be a **licensed mailbox** in your tenant. A shared mailbox also works.

---

## Storage: SharePoint vs OneDrive

Both use the **Microsoft Graph API** and the same Azure AD App Registration (can be shared with email).

### Additional permissions needed
| Storage | Graph Permission |
|---------|-----------------|
| OneDrive | `Files.Read.All` (Application) |
| SharePoint | `Files.Read.All` + `Sites.Read.All` (Application) |

### SharePoint configuration
- **Site URL**: `https://yourcompany.sharepoint.com/sites/yoursite`
- **Default Folder**: `/Documents` (or any library folder)

### OneDrive configuration
- **Drive ID**: Optional. Leave blank for the default organisational drive, or provide a specific drive ID (find with `GET /drives` in Graph Explorer).

---

## Scheduler

Configured in **Settings → Scheduler** or directly in the DB `configs` collection.

| Setting | Default | Description |
|---------|---------|-------------|
| Cron Expression | `0 * * * *` | When to run the reminder check |
| Reminder Interval | `24h` | Min hours between reminders to the same person |
| Max Reminders | `3` | Stop reminding after N times |
| Enabled | `true` | Can be toggled without restarting |

**Live restart** — when you save the cron expression via the Settings UI, the scheduler restarts with the new schedule without a server restart.

**Common crons:**
```
0 * * * *       Every hour
0 9 * * 1-5    9:00 AM Mon–Fri
0 9,17 * * *   9 AM and 5 PM daily
0 */4 * * *    Every 4 hours
```

---

## Approval Workflow

```
Submit Document
     │
     ▼
Create ApprovalRequest (3 stakeholders, each gets a unique UUID token)
     │
     ▼
Send approval emails simultaneously to all 3
     │
     ├── Stakeholder clicks "Approve" → lands on /approve/{token}
     │                               → confirms → status recorded
     │
     ├── Scheduler runs (cron) → checks overdue pending stakeholders
     │                        → sends reminder email (up to maxReminders)
     │
     └── When all 3 approve → status = "approved" → notify submitter
         If any rejects     → status = "rejected" → notify submitter
```

---

## API Reference

### Documents
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/documents` | List (filter: status, search, page) |
| POST | `/api/documents/submit` | Submit for approval |
| GET | `/api/documents/stats` | Count by status |
| DELETE | `/api/documents/:id` | Delete document + approval request |

### Approvals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/approvals` | List requests |
| GET | `/api/approvals/stats` | Stats + reminder count |
| GET | `/api/approvals/token/:token` | Public — get info by token |
| POST | `/api/approvals/respond/:token` | Public — approve/reject |
| POST | `/api/approvals/:id/remind` | Manual reminder trigger |
| GET | `/api/approvals/logs/all` | Full notification log |
| GET | `/api/approvals/scheduler/status` | Scheduler state |
| POST | `/api/approvals/scheduler/run` | Run scheduler now |

### Config
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/config` | Get config (secrets masked) |
| PUT | `/api/config` | Update config |
| POST | `/api/config/test-email` | Send test email |

### Storage
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/storage/files?folder=/path` | List files |
| POST | `/api/storage/test` | Test connection |
