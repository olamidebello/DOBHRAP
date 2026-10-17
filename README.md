# DOBHRAP Business Suite

Self-hosted accounting operations, people records, tax estimates and provider-backed financial workflows. Python 3.11+, SQLite, responsive web GUI, Ansible, systemd and nginx.

This is an actively developed foundation, not a complete QuickBooks, TurboTax or ADP replacement. It now includes real Plaid and Check HTTP adapters. Live operation requires provider credentials, onboarding, permissions and sandbox acceptance testing. No live services have been activated by this commit.

## Implemented features

- Database-backed create/edit/list/search screens for customers, vendors, products, invoices, bills, expenses, projects, employees, time, leave, recruiting, benefits, performance, tax-preparation records, bank review and tasks.
- Password hashes, sessions, CSRF protection, admin/editor/viewer roles, and audit history. New financial integrations are administrator-only.
- Chart of accounts, balanced journals in integer cents, trial balance and CSV export.
- **Banking:** Plaid Link, OAuth redirect resumption, encrypted access tokens, public-token exchange, paginated incremental transaction sync, modifications/removals, disconnect, CSV import and manual category posting. Cursor advances only after all pages succeed; duplicates are skipped. Posting settled USD transactions is explicit and cannot be repeated.
- **Payroll:** Check payroll creation, tax/net-pay preview, provider result review, separate release approval and provider status refresh. Employer, worker, workplace, tax and funding onboarding happen in Check. No local estimate is passed off as live payroll withholding.
- **Tax:** versioned 2026 federal ordinary-income estimates using IRS rates and basic standard deductions. Not a full return engine. Does not calculate credits, capital gains, AMT, self-employment tax, state/local tax or special deduction eligibility.
- **E-filing integration boundary:** durable submission requests, signature/consent references and acknowledgement refresh through a documented custom authorized-gateway contract. No direct IRS transmitter or vendor-specific adapter is supplied. A compatible gateway must be implemented/contracted before this can transmit a return.
- **Workflows:** immutable encrypted payloads, creator submission, independent second-administrator approval/rejection, durable background jobs, source-record change detection, approved invoice/bill ledger posting, recurring operational records and audit events.
- **Operations:** content-addressed releases, pinned dependencies, automated tests before activation, schema initialization, persistent encryption key, restricted services, worker timer, daily consistent database backups and 14-day retention.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Set a private random `DOBHRAP_SETUP_TOKEN` of at least 32 characters and a persistent `DOBHRAP_ENCRYPTION_KEY`. Generate a setup token with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Leave `DOBHRAP_ADMIN_PASSWORD` unset for browser setup. Generate the encryption key with `.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` and store it securely outside the repository. Then:

```bash
.venv/bin/python app.py
```

Open http://127.0.0.1:8080. On first launch, enter the setup token, email, password and confirmation in the setup GUI. It creates a super administrator, signs in, and permanently closes setup. The token is stored only as a hash in the database. Existing accounts are preserved. Legacy environment-password bootstrap remains available when explicitly configured; it creates an ordinary administrator. Create a second administrator through Users for independent financial approvals. Run the worker in another terminal with the identical database, encryption key and provider configuration:

```bash
.venv/bin/python worker.py
```

The worker processes one queued job and one due occurrence per recurring schedule each invocation. The production timer runs every minute. Recurring intervals are days, not calendar months.

## Deploy with Ansible

Clone this repository on a control machine with Ansible. Configure an inventory from `ansible/inventory.example.ini`. Copy `ansible/integrations.example.yml` **outside this repository**, replace bootstrap settings, add provider sandbox credentials and encrypt it using `ansible-vault encrypt`. DNS must point at the server and ports 80/443 must be reachable.

```bash
ansible-playbook -i /path/to/inventory.ini ansible/deploy.yml \
  --ask-become-pass --ask-vault-pass -e @/path/to/encrypted-secrets.yml
```

The playbook installs prerequisites, stages a content-addressed release, installs dependencies, runs tests, backs up the existing database, activates source, starts schema initialization, enables the worker/backup timers and provisions HTTPS. It never generates arbitrary new business logic or downloads unreviewed code at runtime. Schema changes are additive. Existing domain nginx files are retained to preserve Certbot changes; review proxy timeouts on older installations.

Provider options default to sandbox with live switches off. Configure each environment and explicit switch only after provider acceptance testing:

| Vault variable | Purpose |
|---|---|
| `plaid_client_id`, `plaid_secret`, `plaid_env` | Plaid credentials and sandbox/production selection |
| `plaid_redirect_uri` | Registered HTTPS root URL for institution OAuth return |
| `enable_live_banking` | Enables production Plaid requests |
| `check_api_key`, `check_env` | Check sandbox/production API access |
| `enable_live_payroll` | Enables production Check requests; approval still required |
| `efile_gateway_url`, `efile_gateway_token` | HTTPS compatible authorized-gateway configuration |
| `enable_efile_transmission` | Enables outbound filing submission through that gateway |

All credentials belong in Vault, not Git or GUI fields. Ansible generates `/etc/dobhrap-encryption.key` once and never rotates it automatically. Back up that key securely and separately: losing it makes encrypted tokens, workflows and results unreadable.

## Payroll workflow

1. Onboard employer, workers, workplaces, tax parameters, authorizations, historical wages and funding in Check.
2. In **Payroll Processing**, supply Check IDs, dates and earnings; create a draft.
3. Creator opens **Approvals** and submits. A different administrator reviews the exact payload and approves.
4. The worker creates the provider payroll and obtains its calculated preview. Review results in **Jobs**.
5. Create a separate release request referencing the preview job. Submit it and have another administrator approve.
6. The worker checks the provider preview timestamp and sends approval. **Submitted does not mean paid.** Refresh status for actual provider progress.

Check POST requests carry stable idempotency keys. Network ambiguity leaves a job `uncertain`; the worker will not automatically retry financial mutations. Review the provider console before any replacement submission. The app does not yet automate full reconciliation/recovery of unknown provider outcomes or synchronize provider payroll accounting journals.

## Bank workflow

Use **Bank Connections → Connect bank with Plaid**, complete consent in Link, then sync. For OAuth institutions register the configured root HTTPS redirect URL with Plaid; session restoration must be tested with the intended banks. No bank login credentials pass through DOBHRAP. Access tokens are encrypted at rest. Manual synchronization is currently used; webhook-triggered/scheduled bank synchronization is not implemented.

CSV columns are `external_id,date,name,amount,currency`. Dates are ISO YYYY-MM-DD; debits/spending are positive and deposits are negative. Stable external IDs deduplicate per account. Bank posting uses Cash (1000) and the selected category. It does not auto-match existing invoices, payments or other journal entries; avoid posting a second entry for already-recorded activity.

## E-filing and tax boundaries

See [the gateway contract](docs/efile-gateway.md). Tax estimates are never accepted as a filing payload. Filing requires a separately prepared and validated provider return reference, signature authorization reference and taxpayer consent. Two-person approval is required. IRS authorization, transmitter/software testing, provider agreements, return preparation, signature capture, schema validation and the actual gateway/vendor integration remain external prerequisites. A generic REST endpoint is not proof of IRS certification.

## Remaining capabilities

Not yet implemented: full tax-return preparation and all state/year rules; direct IRS e-filing; provider employee onboarding GUI; historical payroll imports; payroll-to-ledger synchronization; complete banking reconciliation and matching; invoice line items/PDFs/payments; COGS/stock movements; calendar-based recurring dates; comprehensive HR/benefits approval rules; MFA/password recovery; full P&L/balance-sheet/cash-flow reporting; automated backup restoration; provider reconciliation after ambiguous outcomes.

Operational invoice/bill records post only through explicit approved workflows. General expense records do not auto-post. Basic product quantities are records, not an inventory ledger. Each workspace has an isolated USD ledger. General records are not field-encrypted; do not put SSNs, bank credentials or tax-document contents in them. Restrict deployment access appropriately for the data you store.

## Verification and operations

```bash
.venv/bin/python -m unittest discover -s tests -v
ansible-playbook -i ansible/inventory.example.ini ansible/deploy.yml --syntax-check
```

Provider tests use mocks and synthetic data. They do not verify live provider access, bank coverage, payroll eligibility, taxpayer consent validity or IRS acceptance. Browser behavior and deployment on a target server must be checked in the intended environment.

Service: `dobhrap`; worker: `dobhrap-worker.timer`; backups: `dobhrap-backup.timer`. Database: `/var/lib/dobhrap/dobhrap.db`; daily backups: `/var/backups/dobhrap`; private environment: `/etc/dobhrap.env`; source: `/opt/dobhrap/current`.

For a manual database recovery, stop the web service and both timers, retain a copy of current data, restore a known-good SQLite snapshot with service ownership, restore the matching encryption key, then restart. A code rollback can repoint `current` at a previous release; do not roll back a database containing newly submitted financial jobs without provider reconciliation. Ansible does not automatically roll back after a failed health check.

## Primary implementation references

- https://plaid.com/docs/transactions/add-to-app/
- https://docs.checkhq.com/docs/payroll-preview-and-approval
- https://docs.checkhq.com/docs/idempotent-requests
- https://www.irs.gov/pub/irs-drop/rp-25-32.pdf
- https://www.irs.gov/publications/p505
- https://www.irs.gov/e-file-providers/modernized-e-file-mef-for-employment-taxes-frequently-asked-questions


## Olamide Olatayo Bello deployment

The supplied OOB logo is served on the sign-in page and workspace. The deployment defaults to `olamideolatayobello.com` on private port 18081.

On the Debian hosting server, run from this repository (install Ansible first if needed):

```bash
ansible-playbook -i 'dobhrap,' -c local ansible/deploy-oob.yml
```

The playbook requires no interactive application password. It generates `/etc/dobhrap-setup.token` with root-only permissions, backs up and replaces this domain's nginx configuration, then configures HTTPS. Existing DOBHRAP accounts are unchanged. DNS must point at this server. Supply your existing encrypted integration settings with `--ask-vault-pass -e @/path/to/encrypted-secrets.yml` to retain configured provider settings; without them deployment uses disabled sandbox defaults. This targets the apex domain only. Review any other enabled nginx files declaring the same domain before running.

## First-run super administrator GUI

After deploying `ansible/deploy-oob.yml`, read the setup token privately on the server:

```bash
sudo cat /etc/dobhrap-setup.token
```

Open https://olamideolatayobello.com/setup and enter the token, your email, a password of at least 14 characters, and confirmation. The first account receives the `super_admin` role. Setup is protected by a custom request header and a one-time server token; an immediate database transaction prevents simultaneous setup attempts from creating multiple owners. Setup cannot be reopened by restarting or redeploying. Do not post the setup token publicly.

Super Admin navigation opens the console for user management, integrations, approvals, reports and audit access. Super administrators can create additional super administrators; ordinary administrators cannot grant that role. All financial operations still require their existing independent approvals. Existing ordinary administrators are not automatically elevated. Business workspaces now use separate databases; platform administration can switch workspace context.

## Automatic diagnosis and repair

On the hosting server, run:

```bash
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/repair-oob.yml
```

This local-only repair inspects the original port, dedicated-service overrides and candidate listeners. It deploys under `oob-business` with a free private port from 18761–18800, retaining that port in `/etc/oob-business.port`. An occupied port is reused only when its owning dedicated process identifies itself as this suite. It never kills unrelated listeners. Conflicting dedicated-suite overrides are backed up under `/var/backups/oob-repair`; a unit name owned by another application causes a clear stop instead of replacement.

Existing provider settings are retained privately, the database is backed up, the encryption key and setup token are preserved, all tests and systemd validation run before service activation, and nginx routing is repaired with backups. Final checks require private and public application identity, HTTPS, the actual logo and active worker/backup timers. A safe report with recommendations is saved at `/var/log/oob-repair-report.json`; `verified: true` appears only after those checks succeed. Network/DNS/certificate failures stop with the failing task; a public success is never inferred from a generic HTTP 200.

Use `repair-oob.yml` for later redeployments so the selected port remains consistent. The legacy `dobhrap` service is left untouched by the repair's service selection; inspect it before retiring it. Do not run a second deployment concurrently. Keep `/etc/dobhrap.env.before-oob-repair`, `/etc/oob-repair-integrations.json`, the encryption key and database snapshots private.

## Registration and multiple business workspaces

Customers can register at `/register` using a business name, email, password and confirmation. Registration creates a new workspace and its administrator; it cannot grant platform super-admin access. The platform must complete `/setup` before registrations are accepted. Login normalizes email case. Registration, setup and login share nginx authentication throttling.

Existing users and records remain in workspace 1. New workspaces use separate SQLite databases under `/var/lib/dobhrap/tenants/tenant-ID.db`. The main database contains the workspace catalog and authenticated users/sessions. Every request resolves workspace membership on the server; changing an ID in a request does not grant access. Tenant administrators create users only in their own workspace. Only platform super administrators may switch workspace context or manage workspace status.

**Super Admin → Tenants** lists workspaces, user counts and status; it creates workspaces with an initial administrator, opens a workspace, and suspends or reactivates it. Suspension blocks existing sessions and new logins and removes the workspace from background processing. Financial two-person approvals remain required inside each workspace. No deletion operation is provided.

Background processing visits every active workspace. Daily backups include the catalog/platform database and each tenant database in its own backup subdirectory. Restore the catalog and the appropriate tenant database snapshots together with the encryption key; each snapshot is individually consistent, and snapshots across workspaces are taken sequentially. Back up the entire tenant directory rather than only the main database.

Platform Plaid, Check and e-filing credentials remain restricted to workspace 1. Newly registered tenants can use local accounting, HR, CSV banking, tax estimates and local invoice/bill approvals; their provider banking, payroll and e-filing operations stay disabled until tenant-specific provider onboarding is implemented. They cannot use or retrieve platform provider credentials.

## Dashboard and navigation

The workspace dashboard reads server-calculated posted revenue, expenses, net income, cash balance, operational invoice/bill totals, staff counts, tasks, leave, workflow/job queues and recent audit events. Financial statements show since-inception profit & loss and a balance sheet with current earnings separated from recorded equity. Operational record totals are never presented as payment settlement or posted financial balances.

Grouped navigation covers overview, platform, sales/customers, purchasing/accounting, people/payroll, banking/tax, automation and administration. It includes module search (Ctrl/Cmd+K), per-user/per-workspace bookmarks, back/home/refresh/print tools, quick creation and role filtering. Record lists support view, edit, duplicate, search, numeric-aware sorting, pagination and CSV export with spreadsheet-formula protection. The tax organizer links return, income, deduction and document-reference screens. The capability catalog lists working workflows, record-only modules, provider integrations and unimplemented areas individually. It does not claim exact ADP, QuickBooks or TurboTax parity.

## Super-admin deployment and commissioning GUI

After one successful root Ansible deployment, **Super Admin → Deployment & commissioning** can queue readiness checks, all-workspace backups, deployment of the installed source, and recommissioning. `/api/platform/status` and `/api/platform/jobs` require a platform super administrator and POST requests require CSRF validation. A single active operation is allowed. There is no browser shell or arbitrary command execution endpoint.

A root-owned `/opt/oob-control` source copy and `/opt/oob-control/admin-runner.py` implement a fixed allowlist of operations. `oob-admin.timer` invokes `oob-admin.service` every 30 seconds after its first invocation. Logs are private under `/var/log/oob-admin`; the GUI shows status and safe summaries. The broker validates the requesting role and canonical job ID again before dispatch. Interrupted operations are marked uncertain rather than retried automatically. Deployment can briefly stop the workspace service. This is privileged host administration: restrict super-admin accounts to trusted server operators.

The GUI deploys the trusted source installed by Ansible, not arbitrary GitHub branches or unreviewed code. To install a new repository version, an operator still pulls the latest code and runs `ansible/repair-oob.yml`; this refreshes the trusted management source. Root installation of the broker is required before GUI management operations become available. The app process runs as `dobhrap-app` and cannot modify the broker source.

## Mobile installation and Android preview

`/downloads` is public and linked from sign-in and workspace navigation. It offers web-app installation with a manifest, app icons and a static-only service worker. Business API data is never cached. Android Chrome and iOS Safari provide their own installation menus when a direct installation prompt is unavailable. Business features require connectivity.

The Android WebView project is in `mobile/`. The `Android preview APK` workflow builds and lints it using Java 17, Gradle 8.9 and Android Gradle Plugin 8.7.3, then publishes the APK to the `android-preview` prerelease. Its workflow runs on changes to `mobile/` or its workflow file, and can also be started manually in GitHub Actions. This is a debug-signed preview, not a production-signed or Play Store release. Signing for production, device testing, publishing and fully native behavior remain separate work. The preview uses a separate application ID and keeps the debug key in the Actions cache for preview upgrade continuity; cache eviction can require reinstalling the preview.

The downloads page checks the published GitHub release before showing the APK link. A queued or failed build is never presented as a downloadable APK. External links open the device browser; provider OAuth and CSV downloads should be verified on the target device. The app is a live-site wrapper with the same account and tenant isolation as the browser.

### Automatic bank imports with user consent

Run on the hosting server inside tmux:

```sh
cd /root/DOBHRAP-oob
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/bank-import-oob.yml
```

The playbook privately prompts for your Plaid client ID and environment-specific secret, repairs the deployment, and installs `oob-business-bank-import.timer`. Register `https://olamideolatayobello.com/` as an OAuth redirect in your Plaid dashboard. Sandbox connects test banks; production requires approved Plaid access and an explicit confirmation. Never enter bank passwords in Ansible or share them in chat. For unattended configuration, provide the prompt variables using an Ansible Vault encrypted vars file, for example `-e @/root/bank-import.vault.yml --ask-vault-pass`.

Sign in to the business workspace, open **Bank connections**, check consent, then choose **Connect bank with Plaid**. Bank authentication and any MFA occur in Plaid Link or the bank's OAuth screen. The current authenticated application's user and workspace own the connection. A short-lived, single-use completion nonce binds each Link flow to that user and workspace. OAuth redirects resume only in the matching browser user/workspace context. Bank cookies and passwords are never collected. Access tokens and PDF documents are encrypted with the persistent deployment key; back up that key separately from the databases.

The first import starts after linking. The timer checks authorized connections every 15 minutes, including active opted-in workspaces, using incremental transaction cursors and duplicate-safe IDs. The bank/provider determines when new data becomes available; this is not a real-time feed. Failed reads retry with an hour backoff. Use **Reconnect bank login** for expired bank authorization, **Pause automatic imports** to stop scheduled reads, or **Disconnect** to revoke the provider connection. Existing connections are not silently opted in; their owner must enable automatic imports. Imported transactions require review and explicit ledger posting.

Optional PDF imports require enabling the **Statements** product during setup and separate user consent when connecting a new bank. Support depends on the institution and Plaid product approval (currently US banks). Available statement PDFs are listed, downloaded with size/checksum validation, encrypted in the workspace database, and downloadable only through authenticated workspace APIs. Each run imports up to ten missing PDFs per connection; remaining files catch up on later runs. Transaction data and bank PDF statements are separate products. The scheduler does not trigger new on-demand statement extractions or bypass bank login/MFA; PDFs not made available by the provider cannot be imported. CSV statement imports remain available as a fallback. To add Statements consent to an older Transactions-only connection, connect again with PDF consent; disconnect the older connection to avoid overlapping feeds.

Settings preserved by future `repair-oob.yml` runs: `enable_auto_bank_import`, `enable_tenant_banking`, `enable_bank_statements`, and existing Plaid settings. Payroll and e-filing stay isolated from this bank-only opt-in. Connection owners (or the platform super administrator) manage connections; authorized workspace administrators can review imported business transactions and PDFs. A suspended workspace is excluded from scheduled imports. The scheduler never posts ledger entries, moves money, or submits payroll.

Check scheduling without exposing secrets:

```sh
systemctl status oob-business-bank-import.timer --no-pager
systemctl list-timers oob-business-bank-import.timer --no-pager
journalctl -u oob-business-bank-import.service -n 30 --no-pager
```
