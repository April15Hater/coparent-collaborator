# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly by opening a private issue or emailing the repository owner. Do not open a public issue for security vulnerabilities.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x.x   | Yes       |

## Security Measures

- Authentication via Cloudflare Access (no passwords stored)
- Append-only comments with SHA-256 hash chain (tamper-evident)
- Security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy)
- AI rate limiting (30 calls per user per hour)
- All user data configured via environment variables (no PII in source)
- Input escaping on all user-rendered content (XSS prevention)
- Parameterized queries via SQLAlchemy (SQL injection prevention)
