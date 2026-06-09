# Document Approval Workflow — SKILL.md

## What This Project Does

A MERN application that manages a **3-stakeholder document approval workflow**. Stakeholders receive email links with unique tokens; they approve or reject without logging in. A cron-based scheduler sends reminders until all respond or the max reminder count is reached.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | Node.js + Express (`server/`) |
| Database | MongoDB via Mongoose |
| Frontend | React 18 + React Router v6 (`client/`) |
| Email | Nodemailer (SMTP) or Microsoft Graph API |
| Storage | Microsoft Graph API (SharePoint or OneDrive) |
| Scheduler | node-cron, DB-driven, live-restartable |

---

## Running the App

```bash
# From repo root — runs server (port 5000) and client (port 3000) concurrently
npm run dev

# Individual processes
npm run server    # Express only
npm run client    # React only
```

The React dev server proxies `/api/*` to `http://localhost:5000` (set in `client/package.json`).

---

## Project Layout

```
approval-workflow/
├── package.json              # Root: concurrently scripts
├── server/
│   ├── server.js             # Entry point — DB connect, routes, error handler, scheduler init
│   ├── .env / .env.example
│   ├── config/
│   │   ├── db.js             # Mongoose connect
│   │   └── seedConfig.js     # Upserts default Config doc on startup
│   ├── models/
│   │   ├── Config.js         # Single-doc: email, scheduler, storage settings
│   │   ├── Document.js       # Document records
│   │   ├── ApprovalRequest.js# Approval + per-stakeholder tokens/status
│   │   └── NotificationLog.js# Audit trail for every email sent/failed
│   ├── services/
│   │   ├── approvalService.js # Create requests, process responses, send emails
│   │   ├── emailService.js    # SMTP + MS365 Graph API sendMail
│   │   ├── schedulerService.js# node-cron wrapper, reads config from DB, live restart
│   │   └── storageService.js  # SharePoint + OneDrive file listing via Graph API
│   ├── controllers/           # Route handlers (thin — delegate to services)
│   ├── routes/                # Express routers for /api/*
│   ├── middleware/
│   │   └── asyncHandler.js    # Wraps async controllers, forwards errors
│   └── templates/
│       └── emailTemplates.js  # HTML templates: initial request, reminder, completion
└── client/
    └── src/
        ├── App.jsx            # Router + sidebar layout; /approve/:token hides sidebar
        ├── components/
        │   ├── Dashboard/     # Stats cards + scheduler status
        │   ├── Documents/     # Document list + submit form
        │   ├── ApprovalTracker/ # Master-detail with timeline + progress bars
        │   ├── Settings/      # Email / scheduler / storage config UI
        │   ├── Approve/       # Public token-based approval page
        │   └── NotificationLogs/ # Full email audit log
        └── services/
            └── api.js         # Axios instance pointing to /api
```

---

## Key Data Models

### `ApprovalRequest`
- `approvals[]` — array of stakeholder sub-docs, each with: `name`, `email`, `status` (pending/approved/rejected), `token` (UUID), `reminderCount`, `lastReminderSent`
- `status` — pending → in_progress → approved | rejected
- `requiredApprovals` — defaults to 3
- Virtual `pendingCount` — derived from `approvals`

### `Config` (single document, upserted on startup)
- `ms365` — Tenant ID, Client ID, Secret, from-email for Graph API email
- `scheduler` — `cronExpression`, `reminderIntervalHours`, `maxReminders`, `enabled`
- `storage` — type (sharepoint|onedrive), Graph API credentials, `siteUrl`, `driveId`, `folderPath`
- `appUrl` — base URL used in email links (e.g., `http://localhost:3000`)

### `NotificationLog`
- One doc per email attempt: `type` (initial/reminder/completion), `recipient`, `status` (sent/failed), `error`

---

## Approval Flow

```
Submit Document
  → Create ApprovalRequest (3 stakeholders, each gets a unique UUID token)
  → Send emails simultaneously to all 3
        Stakeholder clicks link → /approve/{token}
        → POST /api/approvals/respond/:token  { decision: 'approved'|'rejected', comments }
        → approvalService checks if all responded → updates overall status → notifies submitter
  → Scheduler (cron) polls pending stakeholders
        → if lastReminderSent + intervalHours < now AND reminderCount < maxReminders
        → sends reminder email, increments reminderCount
```

---

## API Endpoints

### Documents — `/api/documents`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | Filter: `status`, `search`, `page` |
| POST | `/submit` | Creates Document + ApprovalRequest, fires emails |
| GET | `/stats` | Count by status |
| DELETE | `/:id` | Deletes document + linked approval request |

### Approvals — `/api/approvals`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | List all requests |
| GET | `/stats` | Counts + reminder stats |
| GET | `/token/:token` | **Public** — lookup by token |
| POST | `/respond/:token` | **Public** — approve or reject |
| POST | `/:id/remind` | Manual reminder trigger |
| GET | `/logs/all` | Full NotificationLog list |
| GET | `/scheduler/status` | Current cron state |
| POST | `/scheduler/run` | Trigger scheduler immediately |

### Config — `/api/config`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | Returns config with secrets masked |
| PUT | `/` | Update config; triggers scheduler restart if cron changed |
| POST | `/test-email` | Sends a test email using current config |

### Storage — `/api/storage`
| Method | Path | Notes |
|--------|------|-------|
| GET | `/files?folder=/path` | List files from SharePoint or OneDrive |
| POST | `/test` | Validates Graph API credentials + connectivity |

---

## Email Configuration

### SMTP
Set via Settings UI or directly in `server/.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=you@gmail.com
SMTP_PASS=app-password
SMTP_FROM=no-reply@yourcompany.com
```

### Microsoft 365 (Graph API)
Azure AD App Registration with `Mail.Send` application permission + admin consent.
Config stored in `Config.ms365` (DB), editable via Settings UI.

---

## Storage Configuration

Both SharePoint and OneDrive use Microsoft Graph API. The Azure AD app registration can be shared with email (add `Files.Read.All` + optionally `Sites.Read.All` permissions).

Config stored in `Config.storage` (DB), editable via Settings UI.

---

## Scheduler

- Powered by `node-cron` in `schedulerService.js`
- Config read from DB (`Config.scheduler`) — **no server restart needed** when settings change
- Saving a new cron expression via the Settings UI calls `schedulerService.restart()`
- Default: runs hourly (`0 * * * *`), reminds every 24 h, stops after 3 reminders

---

## Environment Variables (`server/.env`)

```
MONGODB_URI=mongodb://localhost:27017/approval-workflow
PORT=5000
CLIENT_URL=http://localhost:3000
NODE_ENV=development
```

Email and storage credentials are stored in MongoDB (not `.env`) and managed via Settings UI.

---

## Common Development Tasks

**Add a new API route:**
1. Create handler in `server/controllers/`
2. Register in the appropriate `server/routes/` file
3. Add to the API reference table above

**Change email template:**
Edit `server/templates/emailTemplates.js` — functions return HTML strings. The approval link uses `config.appUrl + '/approve/' + token`.

**Add a new React page:**
1. Create component under `client/src/components/`
2. Add a `<Route>` in `client/src/App.jsx`
3. Add a nav entry to the `NAV` array in `App.jsx` if it needs sidebar navigation

**Modify scheduler logic:**
`server/services/schedulerService.js` — the `runCheck()` function queries pending stakeholders and calls `approvalService.sendReminder()`.
