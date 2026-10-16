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

Set `DOBHRAP_ADMIN_EMAIL`, a unique `DOBHRAP_ADMIN_PASSWORD` of at least 14 characters, and a persistent `DOBHRAP_ENCRYPTION_KEY`. Generate the encryption key with `.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'` and store it securely outside the repository. Then:

```bash
.venv/bin/python app.py
```

Open http://127.0.0.1:8080. The first launch creates the administrator. An environment password change does not reset an existing administrator account. Create a second administrator through Users for independent approvals. Run the worker in another terminal with the identical database, encryption key and provider configuration:

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

Not yet implemented: full tax-return preparation and all state/year rules; direct IRS e-filing; provider employee onboarding GUI; historical payroll imports; payroll-to-ledger synchronization; complete banking reconciliation and matching; invoice line items/PDFs/payments; COGS/stock movements; calendar-based recurring dates; comprehensive HR/benefits approval rules; MFA/password recovery; multi-company isolation; full P&L/balance-sheet/cash-flow reporting; automated backup restoration; provider reconciliation after ambiguous outcomes.

Operational invoice/bill records post only through explicit approved workflows. General expense records do not auto-post. Basic product quantities are records, not an inventory ledger. This version is single-company, USD ledger only. General records are not field-encrypted; do not put SSNs, bank credentials or tax-document contents in them. Restrict deployment access appropriately for the data you store.

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
