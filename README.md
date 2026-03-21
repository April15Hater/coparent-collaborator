# Ace's Co-Parenting Board

[![CI](https://github.com/April15Hater/coparent-collaborator/actions/workflows/lint.yml/badge.svg)](https://github.com/April15Hater/coparent-collaborator/actions)
[![Release](https://img.shields.io/github/v/release/April15Hater/coparent-collaborator)](https://github.com/April15Hater/coparent-collaborator/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A shared space for staying organized on everything going on with Ace. Each topic gets its own thread so nothing gets lost, and both parents can respond on their own time.


## How to Sign In

There are no passwords. When you visit the site, you'll be asked to verify your email address — it sends a one-time code to your inbox (similar to how a bank verifies your identity). Enter the code and you're signed in for 30 days. You can also use Google to authenticate. Email addresses have been setup ahead of time and linked to each parents' account.

## Features

### Topics
Each issue gets its own thread. You can see all open topics at a glance, filter by category or status, and sort by priority, date, or recent activity.

**Categories:** Education, Medical, Behavioral, Legal, Scheduling, Financial

**Statuses:** Open, In Progress, Needs Father's Input, Needs Mother's Input, Resolved Together, Closed

**Priority:** Low, Normal, High, Urgent — both parents can change the priority on any topic.

**Sorting:** Priority (default), Recently Updated, Newest First, Oldest First, Due Date

### Updates
Both parents can post updates on any topic at any time. Updates are timestamped and permanent — once posted, they can't be edited or deleted. This keeps the record clear for both sides.

### Tone Adjustment
Before posting an update, you can adjust how it reads using the tone buttons below the text box. Options include Softer, Stronger, Neutral, Professional, Shorter, Longer, More Detail, and Less Detail. This helps both parents communicate clearly without things getting misread or coming across the wrong way. You can always undo a rewrite or edit it further before posting.

If a message might come across as confrontational, a gentle "Heads up" will appear with the option to rephrase it automatically ("Make nice"), edit it yourself, or post it as-is.

### Thread Summary
Click the "Summarize" button on any topic to get an AI-generated summary of the entire conversation so far — helpful for catching up on longer threads.

### Email Notifications
Get an email when the other parent posts an update or changes a topic's status. You can also opt into a daily summary email and due date reminders.

Options:
- Instant alerts when the other parent posts
- Daily digest with a summary of everything that happened
- Due date reminders (7 days, 3 days, and 1 day before)
- Mute specific topics you don't need alerts for

### Due Dates
Topics can have due dates for time-sensitive decisions (hearing deadlines, meeting dates, etc.). Both parents can see upcoming deadlines at a glance.

### Export
Download everything as a CSV (opens in Excel or Google Sheets) or open a printable view you can save as a PDF. Both options are at the bottom of the topics page.

### Practice Topic
There's a "Practice Topic" at the bottom of the list where you can test posting updates, adjusting tone, and changing priority without affecting real topics. It auto-clears every 10 minutes.

## Example Topics

Topics are created based on what both parents need to coordinate on. *(Generalized for privacy.)*

1. School Meeting — Upcoming Parent-Teacher Conference
2. Medical — Therapy Schedule Coordination
3. Schedule Change — Work Night Shifts
4. Behavioral — Consistent Rules Across Households
5. Education — Alternative School Options
6. Device Management — Screen Time & Phone Rules

## Technical Details

Self-hosted FastAPI application with SQLite database. Authentication via Cloudflare Access. Email notifications via SMTP. AI features powered by Claude.

### Setup
```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — set parent emails, Cloudflare Access, SMTP, API keys

# 2. Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Run
uvicorn app.main:app --reload
```

All user accounts, email aliases, and notification recipients are configured via environment variables in `.env` — no emails are hardcoded in the source code. See `.env.example` for all options.
