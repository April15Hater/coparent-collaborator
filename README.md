# Ace's Co-Parenting Board

A shared space for staying organized on everything going on with Ace. Each topic gets its own thread so nothing gets lost, and both parents can respond on their own time.

**Live at:** [coparent.joeysolomon.com](https://coparent.joeysolomon.com)

## How to Sign In

There are no passwords. When you visit the site, you'll be asked to verify your email address — it sends a one-time code to your inbox (similar to how a bank verifies your identity). Enter the code and you're signed in for 30 days. Both of your email addresses work and are linked to the same account.

## Features

### Topics
Each issue gets its own thread. You can see all open topics at a glance, filter by category or status, and track what needs attention.

**Categories:** Education, Medical, Behavioral, Legal, Scheduling, Financial

**Statuses:** Open, In Progress, Needs Joey's Input, Needs Christina's Input, Resolved Together, Closed

### Updates
Both parents can post updates on any topic at any time. Updates are timestamped and permanent — once posted, they can't be edited or deleted. This keeps the record clear for both sides.

### Email Notifications
Get an email when the other parent posts an update or changes a topic's status. You can also opt into a daily summary email and due date reminders.

**Manage your notification preferences** from the API or ask Joey to adjust them.

Options:
- Instant alerts when the other parent posts
- Daily digest with a summary of everything that happened
- Due date reminders (7 days, 3 days, and 1 day before)
- Mute specific topics you don't need alerts for

### Tone Adjustment

Before posting an update, you can adjust how it reads using the tone buttons below the text box. Options include Softer, Stronger, Neutral, Professional, Shorter, Longer, More Detail, and Less Detail. This helps both parents communicate clearly without things getting misread or coming across the wrong way. You can always undo a rewrite or edit it further before posting.

### Due Dates
Topics can have due dates for time-sensitive decisions (hearing deadlines, meeting dates, etc.). Both parents can see upcoming deadlines at a glance.

## Current Topics

These were set up from the March 2026 email exchange:

1. Suspension Hearing & Alternative School Placement
2. 504 Manifestation Determination Meeting (3/24)
3. Therapy Scheduling — Consistent Weekly Sessions
4. Drug Test Results — Documentation
5. Skipping School & Lying About Whereabouts
6. Phone Consolidation — Single Managed Device
7. Schedule Adjustment — Christina's Night Shifts
8. Optima Academy — Alternative Education Option

## Technical Details

Self-hosted FastAPI application with SQLite database. Authentication via Cloudflare Access. Email notifications via SMTP.

### Local Development
```bash
cd shared
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env  # fill in required values
python main.py
```

### Environment Variables
See `.env.example` for all configuration options.
