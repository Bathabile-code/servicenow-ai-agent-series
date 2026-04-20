#!/usr/bin/env python3
"""
EP02 Email Poller — ServiceNow AI Agent Series
----------------------------------------------
Flow: Email arrives in chomi-agent@mails.dev
      → Parse email for customer details
      → Create CSM case in ServiceNow
      → Send confirmation email back to sender

Usage:
    python email_poller.py
"""

import subprocess
import json
import re
import os
import sys
import time
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────
SERVICENOW_INSTANCE = "https://dev228466.service-now.com"
SERVICENOW_USERNAME = "admin"
SERVICENOW_PASSWORD = os.environ.get("SERVICENOW_PASSWORD", "")
SERVICENOW_CASE_TABLE = "sn_customerservice_case"

MAILS_INBOX_CMD = ["mails", "inbox", "--full-id"]
MAILS_INBOX_FULL_CMD = ["mails", "inbox"]

POLL_INTERVAL_SECONDS = 60
PROCESSED_IDS_FILE = Path(__file__).parent / ".processed_email_ids.json"

# ─── Helpers ──────────────────────────────────────────────────────────────

def load_env(path: str = "/home/chomi/.openclaw/workspace/servicenow.env") -> None:
    """Load ServiceNow password from .env file if not already set."""
    global SERVICENOW_PASSWORD
    if not SERVICENOW_PASSWORD:
        env_path = Path(path)
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("SERVICENOW_PASSWORD="):
                    SERVICENOW_PASSWORD = line.split("=", 1)[1].strip()
                    break


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run_mails(args: list) -> subprocess.CompletedProcess:
    """Run a `mails` CLI command and return the result."""
    return subprocess.run(
        ["mails"] + args,
        capture_output=True,
        text=True,
        check=False,
    )


def get_inbox_listing() -> list[dict]:
    """
    Call `mails inbox --full-id` and parse each line into a dict:
    { "id": "<short-id>", "full_id": "<uuid>", "date": "...", "from": "...", "subject": "..." }
    """
    result = run_mails(["inbox", "--full-id"])
    emails = []

    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        # Format: full_id  date  from  subject
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        full_id, date, from_field, subject = parts[0], parts[1], parts[2], parts[3]
        emails.append({
            "id":        full_id[:8],
            "full_id":   full_id,
            "date":      date,
            "from":      from_field,
            "subject":   subject,
        })
    return emails


def get_email_body(email_id: str) -> str:
    """
    Fetch the full email body using `mails inbox <id>`.
    Returns the raw plain-text body.
    """
    result = run_mails(["inbox", email_id])
    # Output format:
    # From: ...
    # To: ...
    # Subject: ...
    # Date: ...
    # Status: ...
    # ---
    # <body>
    lines = result.stdout.splitlines()
    body_started = False
    body_lines = []

    for line in lines:
        if line.startswith("---"):
            body_started = True
            continue
        if body_started:
            body_lines.append(line)

    return "\n".join(body_lines).strip()


def parse_email(body: str) -> dict:
    """
    Extract structured fields from a plain-text email body.

    Expected format (flexible):
        Hi, I need to log a case for a laptop that is not working.
        User: John Smith
        Location: Durban Office
        Issue: Laptop wont boot.
        Priority: High

    Returns dict with keys:
        customer_name, issue_description, location, priority, sender_email
    """
    defaults = {
        "customer_name":     "Unknown",
        "issue_description": "No description provided",
        "location":          "Unknown",
        "priority":          "3",   # 3 = Low in ServiceNow
        "sender_email":      "",
    }

    # Sender / From — email address in angle brackets or bare
    email_match = re.search(r"<([^>]+@[^>]+)>", body)
    if email_match:
        defaults["sender_email"] = email_match.group(1)
    else:
        addr_match = re.search(r"[\w\.\-]+@[\w\.\-]+\.\w+", body)
        if addr_match:
            defaults["sender_email"] = addr_match.group(0)

    # Customer name
    name_match = re.search(r"(?:User|Customer|Name)\s*[:\-]\s*(.+)", body, re.IGNORECASE)
    if name_match:
        defaults["customer_name"] = name_match.group(1).strip()

    # Issue / Description
    issue_match = re.search(r"(?:Issue|Description|Problem)\s*[:\-]\s*(.+)", body, re.IGNORECASE)
    if issue_match:
        defaults["issue_description"] = issue_match.group(1).strip()

    # Location
    loc_match = re.search(r"Location\s*[:\-]\s*(.+)", body, re.IGNORECASE)
    if loc_match:
        defaults["location"] = loc_match.group(1).strip()

    # Priority
    prio_match = re.search(r"Priority\s*[:\-]\s*(.+)", body, re.IGNORECASE)
    if prio_match:
        raw_prio = prio_match.group(1).strip().lower()
        if raw_prio in ("high", "1", "critical", "urgent"):
            defaults["priority"] = "1"
        elif raw_prio in ("medium", "2", "moderate"):
            defaults["priority"] = "2"
        else:
            defaults["priority"] = "3"

    return defaults


def sn_create_case(fields: dict) -> dict:
    """
    Create a CSM case via ServiceNow REST API on sn_customerservice_case.
    Returns the created record dict (includes sys_id, number, etc.)
    """
    payload = {
        "short_description": fields.get("issue_description", "No description"),
        "state":             1,   # 1 = New
        "priority":          fields.get("priority", "3"),
        "description":       fields.get("issue_description", ""),
        "category":          "Customer Request",
    }

    url = f"{SERVICENOW_INSTANCE}/api/now/table/{SERVICENOW_CASE_TABLE}"

    resp = requests.post(
        url,
        auth=HTTPBasicAuth(SERVICENOW_USERNAME, SERVICENOW_PASSWORD),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


def send_confirmation(sender_email: str, case_number: str, short_description: str) -> None:
    """
    Send a confirmation email to the sender via `mails send`.
    """
    subject = f"Case Created: {case_number} - {short_description}"
    body = (
        f"Hi,\n\n"
        f"Your case has been successfully created.\n\n"
        f"  Case Number : {case_number}\n"
        f"  Description: {short_description}\n\n"
        f"Our team will review it and get back to you shortly.\n\n"
        f"Best regards,\n"
        f"Chomi AI Agent 🇿🇦"
    )

    result = run_mails([
        "send",
        "--to",     sender_email,
        "--subject", subject,
        "--body",   body,
    ])

    if result.returncode != 0:
        log(f"[WARN] Failed to send confirmation to {sender_email}: {result.stderr}")
    else:
        log(f"[OK] Confirmation sent to {sender_email}")


def load_processed_ids() -> set:
    if PROCESSED_IDS_FILE.exists():
        try:
            return set(json.loads(PROCESSED_IDS_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_processed_ids(ids: set) -> None:
    PROCESSED_IDS_FILE.write_text(json.dumps(sorted(ids), indent=2))


# ─── Main Poller ───────────────────────────────────────────────────────────

def poll_once(processed: set, dry_run: bool = False) -> set:
    """
    Poll inbox once, process new emails, return updated processed set.
    """
    log("Checking inbox...")
    emails = get_inbox_listing()
    log(f"Found {len(emails)} emails in inbox")

    new_ids = set()

    for email in emails:
        full_id = email["full_id"]
        short_id = email["id"]

        if full_id in processed:
            continue   # already handled

        log(f"Processing: [{short_id}] {email['subject']}")

        body = get_email_body(short_id)
        if not body:
            log(f"[WARN] Empty body for {short_id}, skipping")
            processed.add(full_id)
            new_ids.add(full_id)
            continue

        parsed = parse_email(body)
        log(f"  → Customer: {parsed['customer_name']} | Issue: {parsed['issue_description']} | Priority: {parsed['priority']}")

        if dry_run:
            log(f"[DRY RUN] Would create case: {parsed['issue_description']}")
        else:
            try:
                case = sn_create_case(parsed)
                case_number = case.get("number", "UNKNOWN")
                log(f"[OK] Case created: {case_number}")

                sender = parsed.get("sender_email") or email.get("from", "")
                if sender:
                    send_confirmation(sender, case_number, parsed["issue_description"])
                else:
                    log("[WARN] No sender email found, skipping confirmation")
            except Exception as e:
                log(f"[ERROR] Case creation failed: {e}")

        processed.add(full_id)
        new_ids.add(full_id)

    return processed


def main():
    import argparse
    parser = argparse.ArgumentParser(description="EP02 Email Poller — ServiceNow AI Agent Series")
    parser.add_argument("--dry-run", action="store_true", help="Parse emails but don't create cases or send emails")
    parser.add_argument("--once",   action="store_true", help="Run one poll cycle and exit")
    args = parser.parse_args()

    load_env()

    if not SERVICENOW_PASSWORD:
        log("[ERROR] SERVICENOW_PASSWORD not set. Check /home/chomi/.openclaw/workspace/servicenow.env")
        sys.exit(1)

    log("=== EP02 Email Poller started ===")
    log(f"ServiceNow : {SERVICENOW_INSTANCE}")
    log(f"Table      : {SERVICENOW_CASE_TABLE}")
    log(f"Poll every : {POLL_INTERVAL_SECONDS}s")
    log(f"Dry run    : {args.dry_run}")

    processed = load_processed_ids()
    log(f"Loaded {len(processed)} previously-processed email IDs")

    if args.once:
        processed = poll_once(processed, dry_run=args.dry_run)
        save_processed_ids(processed)
        log("One-shot run complete.")
        return

    while True:
        try:
            processed = poll_once(processed, dry_run=args.dry_run)
            save_processed_ids(processed)
        except Exception as e:
            log(f"[ERROR] Poll cycle failed: {e}")

        log(f"Sleeping {POLL_INTERVAL_SECONDS}s...")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
