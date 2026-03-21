# Changelog

All notable changes to Ace's Co-Parenting Board.

## [v1.1.2] - 2026-03-21

### Fixed
- Topic detail page not loading (JS syntax error from timeline refactor)

## [v1.1.1] - 2026-03-21

### Added
- Version badge in nav bar linking to releases page
- Dynamic version from VERSION file (auto-updates on deploy)

## [v1.1.0] - 2026-03-21

### Added
- Due date management: set, change, or remove due dates on any topic
- Mute/unmute button on each topic for notification control
- Thread collapse: shows last 5 updates with "Show earlier" button
- Long comments truncated with "Show more"
- 10-minute notification cooldown with batched mini-digest

### Fixed
- Notification log field name (was crashing cooldown checks)
- Due date permission model (both parents can manage)
- Mute button state race condition on page load

## [v1.0.0] - 2026-03-21

### Added
- Topic tracker with categories, priorities, due dates, and sorting
- Append-only updates with SHA-256 hash chain (tamper-evident)
- AI tone adjustment (Softer, Stronger, Neutral, Professional, Shorter, Longer, More Detail, Less Detail)
- Appropriateness check with "Make nice" auto-rewrite
- Thread summary (AI-generated)
- Email notifications (instant, daily digest, due date reminders)
- Export (CSV download, printable PDF)
- Priority editing by both parents
- Practice topic with auto-clear
- Cloudflare Access authentication
- Security headers, AI rate limiting
