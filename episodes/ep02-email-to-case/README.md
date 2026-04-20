# EP02 — Email to ServiceNow Case Workflow 🇿🇦

> **Flow:** Email arrives in `chomi-agent@mails.dev` → Parse email → Create CSM case → Send confirmation email

## Overview

EP02 automates the customer support intake flow using the `mails.dev` API and ServiceNow's REST API. Instead of an AI agent reading and deciding on each email, a lightweight Python poller handles the full loop:

```
Email received
      │
      ▼
┌─────────────────────┐
│  email_poller.py    │  ← polls every 60s via `mails inbox`
│  (Python script)    │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Parse email body   │  ← extracts: name, issue, location, priority
│  (regex patterns)   │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  ServiceNow REST    │  ← POST to sn_customerservice_case
│  (CSM Case Creation) │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Confirmation email │  ← `mails send` back to sender
│  (mails CLI)        │
└─────────────────────┘
```

## Prerequisites

- `mails` CLI installed and authenticated (`mk_9cbfc705ccc84e6887a0dffb36763bdd`)
- Mailbox: `chomi-agent@mails.dev`
- ServiceNow PDI: `https://dev228466.service-now.com/`
- Credentials in `/home/chomi/.openclaw/workspace/servicenow.env`:
  ```
  SERVICENOW_PASSWORD=yb*qaLD/T26X
  ```
- Python 3.8+ with `requests` library: `pip install requests`

## How to Run

```bash
# Install dependencies
pip install requests

# Normal mode (runs continuously, polls every 60s)
python scripts/email_poller.py

# Dry-run mode (parses emails, prints what would happen, no API calls)
python scripts/email_poller.py --dry-run

# Single poll cycle (useful for testing)
python scripts/email_poller.py --once
```

## Email Format the Script Expects

The script parses plain-text emails. The format is flexible but it looks for these patterns:

```
Hi, I need to log a case for a laptop that is not working.
User: John Smith
Location: Durban Office
Issue: Laptop wont boot.
Priority: High
```

Supported field labels (case-insensitive):
| Field | Labels | Priority Values |
|-------|--------|----------------|
| Customer name | `User:`, `Customer:`, `Name:` | — |
| Issue description | `Issue:`, `Description:`, `Problem:` | — |
| Location | `Location:` | — |
| Priority | `Priority:` | `High/1/Critical/Urgent` → 1, `Medium/2` → 2, anything else → 3 |
| Sender email | Extracted automatically from `From:` header | — |

## Step-by-Step What Happens

### 1. Poll Inbox
Every 60 seconds the script runs `mails inbox --full-id`. The output looks like:
```
5dea9d4c-1c3d-4169-b3b9-228ff8792995  2026-04-20  18:09  chomi-agent@mails.dev  TEST: ServiceNow Case Creation Request -
```
Each line is split into: `full_id`, `date`, `from`, `subject`.

### 2. Check for Duplicates
Processed email IDs are stored in `scripts/.processed_email_ids.json`. If an email's full UUID is already in this file, it is skipped.

### 3. Fetch Full Email Body
The script calls `mails inbox <short-id>` to get the full email, including body:
```
From: chomi-agent@mails.dev
To: chomi-agent@mails.dev
Subject: TEST: ServiceNow Case Creation Request - Laptop Issue
Date: 2026-04-20 18:09:23.915000+00
Status: sent
---
Hi, I need to log a case for a laptop that is not working. User: John Smith, Location: Durban Office, Issue: Laptop wont boot. Priority: High.
```

### 4. Parse Email
Regex patterns extract structured fields from the body. Falls back to defaults if a field is missing.

### 5. Create ServiceNow CSM Case
A `POST` request to:
```
POST https://dev228466.service-now.com/api/now/table/sn_customerservice_case
Authorization: Basic <base64(username:password)>
Content-Type: application/json

{
  "short_description": "Laptop wont boot.",
  "state": 1,
  "priority": "1",
  "description": "Laptop wont boot.",
  "category": "Customer Request"
}
```

ServiceNow returns the created record including `sys_id` and `number` (e.g. `CS0001003`).

### 6. Send Confirmation Email
Using `mails send`:
```bash
mails send \
  --to john@example.com \
  --subject "Case Created: CS0001003 - Laptop wont boot." \
  --body "Hi,\n\nYour case has been successfully created..."
```

## ServiceNow Fields Reference

| Field | Value | Notes |
|-------|-------|-------|
| `short_description` | From email `Issue:` field | Required |
| `state` | `1` (New) | Set automatically |
| `priority` | `1`–`5` | Parsed from email, defaults to `3` |
| `description` | Same as short_description | Optional but recommended |
| `category` | `Customer Request` | Hardcoded for now |

## Known Limitations

- **No AI parsing** — this is a rules-based regex parser. For complex emails with unstructured text, upgrade to EP03 (AI-powered parsing with an LLM).
- **No retry logic** — ServiceNow API failures are logged but not retried in the same cycle.
- **opened_by field** — left blank. In production you'd look up the sys_user by email address.

## File Structure

```
servicenow-ai-agent-series/
├── scripts/
│   ├── email_poller.py           ← Main script (this episode)
│   └── .processed_email_ids.json ← Auto-created, tracks processed emails
├── episodes/
│   └── ep02-email-to-case/
│       └── README.md              ← This file
└── docs/
    └── setup.md
```

## Credits

Built by [@ThabiAmirchand](https://x.com/ThabiTechy) — ServiceNow Developer | AI Builder | #BuildInPublic

Next: **EP03 — AI-Powered Email Parsing** (coming soon 🌊)
