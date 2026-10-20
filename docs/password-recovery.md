# Account password recovery

Install on the hosting server using the running SQLite or MySQL deployment:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/password-features-oob.yml -e password_issue_recovery=true
```

The installer stages the committed application, tests recovery and server tooling,
reads database settings from the running service process, backs up the active backend
under `/var/backups/oob-password-repair`, creates and verifies recovery tables,
switches releases, and checks local/public HTTPS, JavaScript and backend routes. It preserves backend settings, encryption keys,
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

Recovery tables in the active platform MySQL schema or SQLite database:

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


## Server recovery and backend diagnosis

The live process may use MySQL even while `DOBHRAP_DB` still points at an old
SQLite file. A successful reset against that file does not change the live MySQL
account. `ansible/active_runtime.py` reads the selected service's MainPID and
process environment, uses the app database adapter, and reports only the backend
name and verification result. It refuses a missing SQLite database and never
creates a replacement account catalog. No backend is changed by this playbook.

The default service is `oob-business.service`; use `-e reset_service=dobhrap.service`
only when that is the actual installed web service. Installation preserves existing
passwords. The optional recovery action creates a single expiring link for
`dobcalldemo@gmail.com` (override with `-e recovery_email=owner@example.com`).
Read the link privately with `sudo cat /root/oob-password-reset-link.txt` and open
it within 15 minutes. The root-only file contains a bearer credential; never paste
it into chat or logs. No link is printed by Ansible. Issuing a replacement invalidates
earlier links; the password changes only after completion in the GUI.

All password forms include a Show passwords checkbox to verify typed or pasted
values; setup tokens remain masked. Sign-in, setup, registration, password change
and recovery submit through their existing protected backend endpoints. The mobile
browser regression test follows administrator issuance, reset completion, session
revocation, new-password login and signed-in password change against a temporary
synthetic SQLite database. SMTP delivery and live MySQL operation still require
verification on the target server. Passing a local test is not a deployment result.

