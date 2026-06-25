# BlueprintTracker — Stakeholder Content

This file contains three formats of stakeholder-facing content about the project, all covering the same facts at different levels of depth and purpose.

- [A — One-Page Executive Brief](#a--one-page-executive-brief)
- [B — Slide Deck Outline](#b--slide-deck-outline)
- [C — Detailed Narrative](#c--detailed-narrative)

---

## A — One-Page Executive Brief

### BlueprintTracker — Document Approval Workflow

**What it is.** A self-hosted web application that automates getting a document signed off by its required approvers. Instead of chasing people over email and spreadsheets, you submit a document once, and the system emails each approver a secure personal link, collects their approve/reject decision, automatically reminds anyone who hasn't responded, and notifies the submitter when the outcome is final — with a complete audit trail of every message sent.

**The problem it solves.** Manual approvals are slow and invisible: emails get buried, no one knows who is holding things up, reminders depend on someone remembering to send them, and there's no record of what happened. BlueprintTracker makes the process automatic, trackable, and accountable.

**How it works.**
1. An operator submits a document and names its approvers.
2. Each approver gets an email with their own one-click link — **no account or login required for them**.
3. They approve or reject (optionally with comments) from any device.
4. The system auto-sends reminder emails on a schedule until everyone responds or a limit is reached.
5. When all approve, the document is marked approved and the submitter is notified; if anyone rejects, it's marked rejected.
6. A live dashboard shows status, progress, and who still needs to act.

**Key benefits.**
- **Faster cycle times** — automated reminders remove the human bottleneck of follow-up.
- **Full visibility** — dashboard and timeline show exactly where each approval stands.
- **Accountability & audit** — every email (sent or failed) is logged.
- **Zero friction for approvers** — they just click a link; nothing to install or log into.
- **Fits your Microsoft environment** — sends from your Microsoft 365 mailbox and can connect to SharePoint/OneDrive.

**Current status.** Functional end-to-end. Documents are attached via URL link today; the SharePoint/OneDrive browse-and-upload feature is built and can be re-enabled. Access is protected by an admin login. Deployable to cloud hosting (Railway or Vercel).

**Built on.** A modern, widely-supported web stack (React, Node.js, MongoDB) with Microsoft 365 integration — no exotic technology, easy to host and maintain.

**Suggested next steps.** Refresh documentation; decide on the storage experience (URL-only vs. re-enabling SharePoint/OneDrive browse); and, if it will serve multiple teams, plan for individual user accounts (today there is one shared admin login).

---

## B — Slide Deck Outline

> ~11 slides. Designed for a 10–15 minute walkthrough to a mixed audience. Technical depth is concentrated in slides 7–9 and the optional appendix.

**Slide 1 — Title**
- BlueprintTracker: Automated Document Approval Workflow
- Tagline: *"Submit once. The system chases approvals, tracks status, and keeps the record."*

**Slide 2 — The Problem**
- Approvals today: email threads, manual follow-up, no central status view.
- Pain: things stall silently, no accountability, no audit trail, reminders depend on memory.

**Slide 3 — The Solution**
- A web app that routes a document to its approvers and manages the whole cycle automatically.
- Submit → notify approvers → collect decisions → auto-remind → finalize → notify submitter.

**Slide 4 — How It Works**
- 6-step flow: Submit → Email links to approvers → Approve/Reject (no login) → Auto-reminders → All approve / any reject → Submitter notified.
- Key point: approvers just click a secure personal link — nothing to install or sign up for.

**Slide 5 — Key Features**
- Dashboard: live stats, scheduler status, recent activity.
- Approval Tracker: per-approver timeline, progress bars, manual "remind now," stop/resume per request.
- Full notification audit log (every email, sent or failed).
- In-app Settings — configure email, schedule, and storage without code changes or redeployment.

**Slide 6 — Benefits / Value**
- Faster approvals, less manual chasing.
- Complete visibility and accountability.
- Frictionless for approvers.
- Tamper-evident audit trail.
- Integrates with existing Microsoft 365 / SharePoint / OneDrive.

**Slide 7 — Architecture** *(technical)*
- MERN stack: React front end · Node.js + Express API · MongoDB database.
- Background scheduler (cron) drives automated reminders.
- Microsoft Graph API for sending mail and (optionally) reading SharePoint/OneDrive files.
- Clean separation: models / services / controllers / routes.

**Slide 8 — Integrations & Storage** *(technical)*
- Email: sent from a Microsoft 365 mailbox via Graph API (OAuth2).
- Document attachment: URL Link (active today); SharePoint/OneDrive browse-and-upload (built, currently disabled).
- Requires an Azure AD app registration with scoped Graph permissions.

**Slide 9 — Security & Access** *(technical)*
- Secure-by-default: all API routes require auth except a small explicit public allow-list.
- Admin area: JWT login, 24-hour tokens, credentials from environment variables.
- Approvers: unique per-person tokens embedded in email links — no shared password.
- Secrets masked in UI, excluded from source control; system fails loudly if misconfigured.
- Transparency: single shared admin credential, no MFA, no rate-limiting yet (known roadmap items).

**Slide 10 — Deployment & Status**
- Railway (always-on, built-in scheduler) or Vercel (serverless + scheduled cron trigger).
- Status: working end-to-end; URL-link document attachment live; admin login in place.

**Slide 11 — Roadmap / Next Steps**
- Re-enable SharePoint/OneDrive browse-and-upload (decision needed).
- Multi-user accounts & roles (currently one shared admin login).
- Security hardening: MFA, login rate limiting, approver token expiry.
- Documentation refresh (README predates login and cloud-deploy features).

**Appendix (optional technical slides)**
- Data model summary: Document, ApprovalRequest (with per-approver records), Config, NotificationLog.
- API surface: auth / documents / approvals / config / storage / health.

---

## C — Detailed Narrative

### 1. Purpose

BlueprintTracker automates document sign-off. It replaces ad-hoc email chains and manual follow-up with a single, trackable, auditable workflow. An operator submits a document and assigns its approvers; the system handles notification, reminders, decision collection, finalization, and record-keeping.

### 2. The Problem It Addresses

In most organizations, document sign-off relies on email and personal diligence. Requests get buried in inboxes, no one has a single view of who is holding up a decision, reminders only happen if someone remembers to send them, and once it's done there's no reliable record of who approved what and when. BlueprintTracker turns this into a structured, automated process with end-to-end visibility and a permanent audit trail.

### 3. How It Works

1. **Submit** — The operator submits a document and names its approvers. The document can be attached by URL link today; SharePoint/OneDrive browsing is built and can be re-enabled.
2. **Notify** — The system creates an approval request and emails each approver a **unique secure link** to their personal approval page. Approvers need no account or password.
3. **Decide** — Each approver opens their link, approves or rejects with optional comments, from any device.
4. **Auto-remind** — A background scheduler sends reminders on a configurable interval up to a configurable maximum. Operators can also trigger reminders manually, or stop/resume reminders for a specific request.
5. **Finalize** — All approve → document marked **approved**, submitter notified. Any reject → document marked **rejected**, submitter notified.
6. **Track** — A dashboard and detailed approval tracker show real-time status, a per-approver timeline, progress bars, and the full notification history.

> The workflow is currently fixed at **three approvers** per document.

### 4. Core Features

| Feature | What it does |
|---|---|
| Dashboard | Stats overview, scheduler status with "run now," recent activity |
| Submit Document | Assign approvers, attach document via URL; prevents duplicate approvers |
| Approval Tracker | Per-approver status, timeline, progress bars, manual reminders, stop/resume |
| Notification Logs | Full audit log of every email — sent or failed, with error details |
| Settings | Runtime configuration of email, scheduler, and storage — no redeploy needed |
| Public Approval Page | Friction-free, no-login page for approvers |

### 5. Architecture

BlueprintTracker is a **MERN** application:

- **Frontend** — React 18 single-page app (React Router, Axios).
- **Backend** — Node.js with Express, organized into layers: `models/` (data schemas), `services/` (business logic), `controllers/` (request handling), `routes/` (API endpoints), `middleware/` (auth).
- **Database** — MongoDB via Mongoose (local or MongoDB Atlas in the cloud).
- **Scheduler** — `node-cron` runs the automated reminder job; configuration is reloaded on each tick so live changes take effect without a restart.
- **Email & files** — Microsoft Graph API for email dispatch and optional SharePoint/OneDrive file access.

**Primary data entities:**

| Entity | What it represents |
|---|---|
| Document | The item under approval: name, URL, storage type, status, submitter |
| ApprovalRequest | The workflow record for one document; embeds one record per approver (name, email, status, unique token, comments, reminder tracking) |
| Config | Singleton settings for email, scheduler, and storage |
| NotificationLog | One entry per email sent or attempted — the audit trail |

### 6. Integrations & Storage

- **Email** — Sent via Microsoft 365 Graph API (OAuth2 client-credentials flow). Every send is logged.
- **Document attachment:**
  - **URL Link** — paste any document URL; active and in use today.
  - **SharePoint / OneDrive browse-and-upload** — fully built (file listing, drag-and-drop upload, progress bar, file-size/type limits) but currently disabled in the UI pending a product decision.
- **Prerequisite** — An Azure AD app registration with appropriately scoped Microsoft Graph permissions (`Mail.Send`, `Files.Read.All`, etc.).

### 7. Security & Access Control

**Strengths:**
- **Secure-by-default API** — Global auth middleware protects all endpoints; the public allow-list is small and explicit (login, health check, approver-facing endpoints).
- **Admin login** — JWT-based, 24-hour tokens; credentials sourced from environment variables.
- **No weak fallback** — The system refuses to operate if `JWT_SECRET` is unset rather than silently falling back to an insecure default (a real vulnerability that was patched).
- **Secret hygiene** — Sensitive values (mail/storage client secrets) are masked in API responses and never echoed back; secrets are excluded from source control.
- **Per-approver tokens** — Each approver's link carries a unique, unguessable UUID token scoped to one request, so approvers need no shared credential.
- **CORS allow-list** — API access is restricted to configured front-end origins.

**Known limitations (roadmap items):**
- Single shared admin account — no per-user accounts, roles, or MFA.
- Admin token stored in browser localStorage (vs. a more secure httpOnly cookie).
- Approver tokens do not currently expire.
- The scheduler-trigger endpoint is public (low risk — it only sends reminders).
- No login rate-limiting or lockout yet.

### 8. Intended Users

- **Operator / administrator** — The logged-in user who submits documents, configures integrations, and monitors approvals. Designed today for a single team with one shared credential.
- **Approvers** — The three reviewers per document who receive email links and respond without logging in.
- **Submitters** — People whose documents go through approval (recorded as metadata).

The Microsoft 365 / SharePoint / OneDrive orientation indicates an enterprise Microsoft-based organization.

### 9. Deployment

| Option | Scheduler | Notes |
|---|---|---|
| **Railway** (always-on) | Built-in `node-cron` runs continuously | Health check at `/api/health`, auto-restart |
| **Vercel** (serverless) | Vercel Cron triggers the scheduler endpoint | Frontend served as static SPA |
| **Local development** | Single `npm run dev` | API on :5000, React on :3000 |

### 10. Current Status & Next Steps

**Status:** Working end-to-end. Admin login in place. Documents attached via URL link. SharePoint/OneDrive browse-and-upload is built but disabled in the UI.

**Recommended next steps:**
1. **Storage decision** — Keep URL-only, or re-enable SharePoint/OneDrive browse-and-upload.
2. **Multi-user support** — Add individual accounts and roles if more than one team will use it.
3. **Security hardening** — MFA, login rate-limiting, approver-token expiry, httpOnly cookie for the admin token.
4. **Documentation refresh** — The README predates the admin-login and cloud-deployment features.
5. **(Optional) Naming** — The repo is "BlueprintTracker" while the product is a generic document approval workflow; decide whether to align them.
