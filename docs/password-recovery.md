# Account password recovery

Install on the hosting server using the existing MySQL deployment:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/install-password-reset-oob.yml
```

The installer stages the committed application, tests the recovery logic, switches
releases, restarts the web service to initialize the new tables, and checks local
HTTPS and existing account setup. It preserves backend settings, encryption keys,
users, roles and data. A failed health check restores the previous app release.

The sign-in page links to `/forgot-password`. Email links open
`/reset-password#token=...`; the fragment never reaches access logs and is removed
from browser history when the form opens. Tokens expire after 15 minutes, are
stored only as SHA-256 hashes, and become invalid after use or a newer request.
A password update rotates the scrypt salt and revokes every existing session.
Passwords must contain 14–1024 characters and match the confirmation.

Self-service delivery requires SMTP settings. A super administrator can configure
**Provider provisioning & keys → Password recovery email** with SMTP host,
port, sender, security (`starttls` or `tls`) and optional username/password.
Saved settings are encrypted using the existing platform encryption key. Only a
super administrator with their current password can edit them. SMTP credentials
are never returned to the GUI. The default secure port is 587 (STARTTLS) or 465
(TLS). Certificates are verified. Real email delivery still needs a configured
and reachable mail provider; no SMTP account is automatically created.

Without SMTP, administrators can use **Users → Account password recovery** to
create a link and copy it for private delivery to the owner. Tenant admins can
only issue links for their own workspace and cannot reset a super administrator.
Super administrators can issue links across workspaces. Issuance requires the
administrator's current password and the signed-in CSRF token. The raw link is
returned once and is never stored in audit records.

Signed-in users have a **Change password** button beside Sign out. Changing a
password requires the current password and signs out every session. Email
recovery uses a generic response for known and unknown accounts. Email requests,
invalid reset attempts and password confirmation attempts have database-backed
rate limits. Failed email delivery invalidates its token and records a safe audit
event without SMTP error details or reset tokens.

New tables in the platform MySQL schema (or SQLite in development):

- `password_resets`: token digest, owner, expiry, used flag and delivery state.
- `password_reset_limits`: hashed rate-limit key, count and window start.

API routes:

- `POST /api/password-reset/request`: email, custom recovery header.
- `POST /api/password-reset/complete`: token, password, confirm_password, custom header.
- `POST /api/password-reset/admin`: email, current_password; authenticated and CSRF protected.
- `POST /api/password/change`: current_password, password, confirm_password; authenticated and CSRF protected.

The public custom header is `X-Password-Reset-Request: 1`. Reset links always use
the fixed HTTPS site origin, never the request Host header. Existing disabled
workspace and role restrictions remain in place after recovery.
