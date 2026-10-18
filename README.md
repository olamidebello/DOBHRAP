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

### Payment gateways and service marketplace

On the hosting server, deploy the marketplace with:

```sh
cd /root/DOBHRAP-oob
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/marketplace-oob.yml
```

The playbook privately collects Stripe and/or Paystack secret keys, validates their test/live prefixes, and confirms API access with read-only balance requests. Live payments require an explicit live-mode confirmation. It builds and tests the release, deploys the database/API/GUI, and verifies the public HTTPS marketplace configuration and `oob-business-marketplace.timer`. A merchant account and provider approval are required; Ansible does not perform merchant identity verification or fabricate credentials. For unattended setup, store `market_payment_environment`, `market_live_confirm`, `market_stripe_key`, `market_stripe_webhook_secret`, and `market_paystack_key` in an Ansible Vault encrypted file and pass `-e @/root/marketplace.vault.yml --ask-vault-pass`. Empty keys disable the respective gateway during this setup. Normal repair runs retain previously installed gateway settings.

Stripe webhook registration is automatic: the playbook finds the exact application endpoint, creates it when absent, enables the selected Checkout events, and immediately saves the newly returned signing secret in a root-only file. It reuses the saved secret on subsequent runs. If the endpoint predates this installation and its secret is not saved locally, provide its existing `whsec_...` signing secret from Stripe. Ambiguous endpoint inventories stop before creating duplicates. The script does not create a payment to test the connection.

Webhook endpoints:

- Stripe: `https://olamideolatayobello.com/api/market/webhooks/stripe` — `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`.
- Paystack: `https://olamideolatayobello.com/api/market/webhooks/paystack` — set this in your Paystack merchant dashboard for the selected environment. This integration does not claim to automate that dashboard setting.

The GUI has **Service marketplace**, **Marketplace orders**, **Purchased services**, and **Marketplace administration**. The super administrator creates/edits/publishes/archives offers, sets prices in cents or kobo, and manages the fulfillment queue. No paid offers or recommended prices are published automatically. Supported checkout pairs are Stripe/USD and Paystack/NGN; additional gateways/currencies require adapters. Offers are one-time platform service packages, such as accounting support or office onboarding. They are not recurring subscriptions, a reseller marketplace, inventory shipping, automatic payroll execution, or server hosting provisioning.

Workspace administrators purchase through provider-hosted checkout; card data is never collected by the application. The backend snapshots the catalog price and service code into the order and ignores browser-supplied totals. Checkout requests have a workspace/user-bound idempotency key. Stripe initialization retries reuse the original order ID as the provider idempotency key; Paystack uses a unique order reference. After an uncertain old Stripe initialization, automatic reinitialization is blocked before its idempotency window expires. Reconcile unknown outcomes before making another order. Signed callbacks are verified against the exact raw payload (Stripe timestamp/HMAC-SHA256 or Paystack HMAC-SHA512), deduplicated, and durably scheduled. The timer independently checks pending orders even if a callback is missed. A checkout return URL never establishes payment success.

Payment verification retrieves the payment from the selected merchant API and checks successful payment, reference, exact integer amount, currency and test/live environment. Only then does one database transaction activate a purchased service record and enqueue it for fulfillment, once per order. A test payment creates `test_fulfilled` / `test_active` records, separate from live services. Workspace suspension prevents service activation; verification retries preserve pending paid orders for later fulfillment. Human services must still be delivered by staff, whose queue states are new/in progress/completed/suspended. These service records do not change existing module permissions or imply that a human service has already been delivered.

Super admins see all orders and service delivery states; other users only see their workspace's orders and services. Only workspace administrators can initiate purchases or request payment verification. Product administration and fulfillment updates require the platform super administrator. Gateway keys remain in the root-only environment file, never in the GUI or source. The admin gateway table distinguishes configured signing keys from the last successfully authenticated callback. Credential checks do not prove webhook delivery: complete a provider test checkout and confirm its order plus signed event before enabling production.

Refunds, disputes, merchant settlement, taxes on sales, and reseller payouts are not automated. Reconcile them in the provider console and suspend the affected purchased service in the GUI. Switching payment environments pauses automatic reconciliation of orders from the other environment. Automatic confirmation polls up to twenty due orders per run, with retry delays on unavailable or mismatched provider responses. It does not debit a card, retry a charge, issue a refund, or post accounting journals.

Check the scheduler:

```sh
systemctl status oob-business-marketplace.timer --no-pager
journalctl -u oob-business-marketplace.service -n 30 --no-pager
```

### Super administrator provisioning, credentials and API profiling

Run this on the hosting server to install the GUI, support worker and credential provisioning:

```sh
cd /root/DOBHRAP-oob
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/provision-gui-oob.yml
```

The playbook builds/tests the release, preserves persistent encryption/setup secrets, creates a support integration token only when absent, verifies the service timers and frontend, and profiles configured OpenAI/Stripe/Paystack/Plaid API access with read-only calls. Results and connection timings are saved to `/var/log/oob-provision-readiness.json` and the GUI. It does not invent provider keys, create merchant accounts, purchase services, or complete merchant KYC. Unconfigured providers remain visibly unconfigured. The database and its separately backed-up encryption key are needed to recover encrypted provider credentials.

After first-run super admin setup, open **Provider provisioning & keys**. The console lets the platform super administrator configure keys, environments, model selection and financial feature switches; check provider access; provision the Stripe endpoint; rotate a support intake token; and inspect database/queue readiness and connection timings. Confirm the current administrator password for changes and checks. Enabling live financial operations requires an additional explicit confirmation. Saved keys are encrypted, masked by presence, never returned by read APIs, and never placed in audit messages. Blank key inputs preserve values; Disable creates an empty override. GUI values override server environment values and are read by the web service and background workers without changing shared process environment or requiring a restart. Account creation and API keys still come from each provider's own account pages, linked in the GUI. No OpenAI key needs to be created in ChatGPT for this workflow.

The **Generate / rotate support integration token** action returns only the newly generated token once, in a masked field with Copy/Dismiss controls. Save it in your external automation's secret store. Read APIs cannot recover it; rotating invalidates the old token. The initial generated operator copy is root-only at `/etc/oob-support-intake.token`; after GUI rotation that original copy is obsolete. `/etc/oob-marketplace-webhook.json` is also an operator-side record; GUI Stripe signing-secret overrides take precedence.

The profiler reports configured providers, read-only connection test outcomes and elapsed milliseconds, database integrity, active workspace count and pending support/payment work. It does not measure billing cost, guarantee provider permissions beyond the tested endpoint, confirm webhook delivery, or certify that a merchant is approved for live sales.

### User manual, support tickets and AI automation

Open **User manual** to search product guidance and download the manual, or see [docs/USER-MANUAL.md](docs/USER-MANUAL.md). **Support center & tickets** supports ticket creation, priorities, conversation history, replies, close/reopen, human escalation, AI consent revocation and AI job status. Users see their own tickets; workspace administrators see workspace tickets; platform super administrators see all tickets and can reply as staff. Cross-workspace requests are rejected. Support remains available when no AI key is configured. Tickets/messages are backed up with the central database. Attachments, email delivery and external chat connectors are not included.

To activate AI assistance, save an OpenAI API key and a Responses-compatible model ID available to your project in the provisioning console; run its model-access check, then enable AI support. Automatic AI replies are a separate optional switch. Each customer must explicitly consent for that ticket to send its conversation to OpenAI. The agent receives only the product manual and a bounded excerpt of that ticket's conversation, requests no provider-side response storage, uses at most 800 output tokens per request, has no action tools and cannot change accounts, permissions, keys, deployment or financial records. Replies are labelled AI; review suggestions and escalate for human help. Configure your OpenAI project's spend limits separately. The implementation caps AI jobs at 30 per workspace per rolling day and one job per customer message. Failed/uncertain paid requests are not automatically retried. Human escalation or consent revocation cancels queued work; in-flight requests cannot be unsent, and their answers are discarded if consent or ticket eligibility changes.

`oob-business-support.timer` runs each minute. It processes one queued AI reply per run and flags unanswered open tickets for human escalation after four hours for high priority or 24 hours otherwise. These are local queue rules, not a promise of staff response time. No email, Slack or other outbound messages are sent.

For external automation, configure or generate a **Support webhook token** in the super admin GUI, then POST to `/api/support/intake` with `Authorization: Bearer <your token>` and JSON fields `tenant_id`, `subject`, `message`, and optional `priority` (`low`, `normal`, `high`). The workspace must exist and be active. The API only creates a ticket and does not execute commands. Integration intake cannot grant AI consent for another person; its tickets are for workspace/platform administrators. Never include credentials, SSNs, card numbers or bank account numbers in support conversations.

### Global language, currency and regional preferences

The **Language & currency** screen persists each signed-in user's locale, preferred display currency and IANA time zone. Babel/Unicode CLDR supplies 1,066 locale variants and 305 currency codes in the pinned release, including historical/special units; this is not a claim to translate every human language. Native and English locale names are searchable through the browser's selector. Arabic and other right-to-left locales set document direction and adapt layout. Interface amounts and supported date/timestamp cells use regional formatting. Currency minor units follow CLDR (for example, JPY 0 and KWD 3). These preferences do not alter another user's settings or change stored records.

Initial core navigation/button translations cover English, Spanish, French, Arabic, Portuguese, German, Chinese, Hindi, Yoruba, Hausa, Igbo and Swahili. Translation coverage is deliberately displayed separately from locale availability: untranslated text falls back to English. The application does not claim fully translated payroll, tax forms, manuals, support conversations or provider screens. Super administrators can import plain-text phrase-to-translation JSON for any available locale, export the current phrase catalog, and remove an override by supplying an empty value. Locale-specific entries override language-level seed translations. Uploaded HTML is rejected; customer data is never automatically translated.

The ledger, existing operational totals and US tax/payroll calculations remain USD-based. Changing a preferred display currency never substitutes a currency symbol over an unconverted ledger amount. Super administrators may configure a positive reference rate (target units per one USD), effective date and source. A configured rate can display an explicitly approximate converted amount alongside its original USD amount. Rates older than seven days stop converting; absent/stale rates display the original USD. No live exchange-rate feed is configured, and reference rates never price a checkout, settle a payment, or post an FX journal. This is display/reference support, not full multi-currency accounting or global tax compliance.

Marketplace offers may record recognized currencies and format their integer minor-unit prices accordingly. Checkout remains limited to the implemented Stripe/USD and Paystack/NGN combinations; unsupported settlement currencies show payment unavailable. No customer payment is converted automatically. Currency formatting and locale selection do not establish a provider's currency, jurisdiction or language availability.

Deploy using the existing `ansible/provision-gui-oob.yml` playbook; it installs the pinned Babel dependency and the internationalization API/frontend assets. No additional provider key is required for locale catalogs or formatting.


### Private 2026 tax preparation
Tax → Tax preparation → 2026 Tax Return provides a saved, encrypted slide interview, supporting document storage, CSV income intake, approved workspace-record imports, review and worksheet export. Opt-in GUI-configured AI reviews a redacted summary for potential deduction/credit questions. This is preparation intake with a limited ordinary-income estimate, not a complete tax/refund engine or e-file return. See the user manual for scope and privacy details. Existing workspace databases migrate on application startup.


### Tax analyst and tax-only registration
**Tax → Tax preparation → 2026 Tax Return → Tax analyst** stores private PDF/JPEG/PNG statements and receipts, extracts proposed transactions using a GUI-configured document-capable OpenAI model with explicit full-document consent, and supports manual correction, classification and approval. Compile approved USD records into yearly preparation snapshots; Compilations for the current tax year and prior five years create guided preparation drafts. No complete tax calculation, refund guarantee or official filing package is generated.

The public `/tax-services` link registers a personal tax-only account without a company name. Business APIs and navigation are denied. Tax-only users can upload/review documents before payment, but must purchase a **live verified** `tax_preparation_YEAR` offer before creating, compiling or exporting a preparation. A super admin publishes offers and prices in Marketplace administration and configures live gateway credentials through the provider console. Test payments do not unlock access. Preparation access does not imply IRS e-file availability.


Super admin **Coupon management** issues full-service vouchers with expiry, usage caps, service/email restrictions and redemption auditing. Users choose **Pay with coupon** in the marketplace. Valid vouchers activate the service atomically without a gateway charge and can satisfy the tax-only year-specific payment requirement. Partial discounts and cash-value balances are not implemented.


### Upload a complete tax document collection
Tax analyst accepts multiple PDF, PNG and JPEG uploads, up to 2 MB each and 100 files / 100 MB per owner. Choose Auto or identify W-2, 1099-INT/DIV/NEC/MISC/K/R/B, SSA-1099, 1098/T/E, 1095-A, K-1, prior-year returns, estimated payments, charity evidence, business records or Other tax document. This list describes intake categories, not complete tax calculation support. Export Word/Excel or other files to PDF before upload. Use separate files for separate tax forms and redact unnecessary identifiers.

Select full-document AI consent and Analyze automatically after upload, or use Analyze pending documents after saving the collection. The existing one-hundred-analysis-per-user daily limit applies; uploaded files remain saved when analysis is disabled, fails or reaches the limit. Review batch results and retry pending documents explicitly after resolving the issue. No automatic paid retries occur.

AI separates transaction entries from tax-form box fields. Edit form name, box, label, value, currency, tax year and source reference, then approve verified fields. Unknown years must be confirmed, and fields from a prior-year return must not be approved as current-year amounts. AI does not extract personal identifiers into structured tax fields. Review originals for missing or incorrect amounts.

Compilation automatically maps approved USD W-2 boxes 1/2, 1099-INT boxes 1/4 and 1099-DIV boxes 1a/1b/4 into the supported income interview. These box mappings use the IRS forms at https://www.irs.gov/pub/irs-pdf/fw2.pdf, https://www.irs.gov/pub/irs-pdf/f1099int.pdf and https://www.irs.gov/pub/irs-pdf/f1099div.pdf. Other approved fields are preserved in the compilation JSON for manual preparation; they do not automatically compute credits, itemized deductions, retirement taxability, capital gains, business tax or state returns. Avoid approving both bank deposits and tax-form amounts for the same income.


### Lawful refund optimization review
In the 2026 interview Review slide, choose **Calculate supported refund projection & review opportunities**. The deterministic calculation uses entered income, federal withholding, estimated/extension payments and prior-year applied credits, with explicit verification and duplicate checks. AI can suggest documentation/eligibility questions but cannot change the arithmetic or invent tax benefits.

The current numerical comparison supports narrow simple single-filer estimated-tax scenarios (age 25–64, ordinary supported income below $200,000, no other taxes/credits/adjustments or unsupported situations): standard deduction versus standard deduction plus up to $1,000 of verified eligible 2026 cash charitable donations for non-itemizers. Confirm organization eligibility, actual payment and records; excluded gifts such as donor-advised fund donations do not qualify. Estimated refund/balance and the tax reduction between supported scenarios are displayed, with the formula inputs and IRS sources. The calculation follows 2026 estimated-tax rate schedules and may differ from final return tax-table results.

Missing data, uncertain eligibility and unimplemented situations block the projection. The opportunity checklist includes itemization, dependent/EITC/education/adoption benefits, retirement/HSA/student-loan deductions, business/investment rules, carryforwards and 2026 special deductions. These are review topics, not automatically awarded benefits. No complete itemized deduction, state tax, AMT, NIIT, self-employment, credit or penalty computation is provided. Results are saved privately and invalidated when interview data changes. No globally maximum refund or filing-ready return is certified. Sources: IRS Publication 505 (2026), https://www.irs.gov/publications/p505; Publication 6196 (10-2026), https://www.irs.gov/pub/irs-pdf/p6196.pdf; Rev. Proc. 2025-32.


## Six-year preparation, amendments and production marketplace
The year catalog rolls automatically to the server current year plus five prior years (2026–2021 at this release). Tax analyst and Tax returns provide dropdown selectors, and Prepare all years with approved records creates separate private drafts for eligible selected years. Payment/coupon access is required for each tax-only account/year. Unsupported or incomplete years are reported separately. No uploads are silently copied across years.

The versioned IRS-source registry includes ordinary-income brackets and single-filer standard deductions for 2021–2026, including the updated 2025 $15,750 deduction. These are limited estimated-tax projections, not complete yearly Form 1040 calculations. The supported charitable scenario currently applies only to the verified 2026 non-itemizer provision; older-year charitable and other unimplemented benefits require qualified preparation. The system does not reuse current-year rules for an unavailable year. Refund projections remain conditional and never certify a global maximum.

Open Amended tax preparation, choose the year and upload the originally filed return plus supporting corrections through Tax analyst. Approve 1040 fields labeled Adjusted gross income, Taxable income, Total tax and Total payments to import an original summary. Enter corrected figures from a validated preparer, or import the explicitly limited saved projection from a same-year owned draft. Save an explanation and review original/change/corrected columns. Download the worksheet for a preparer. These comparisons are not the complete 1040-X refund calculation; original refunds/credits, IRS adjustments, later payments, claim deadlines, amended schedules and signatures require reconciliation.

On the preparation Review slide, opt in to automatic redacted-summary AI suggestions. Saving queues a durable background opportunity review, coalesces older pending revisions, checks user/workspace access and applies five-minute / twenty-per-user daily limits. The financial worker processes up to three paid suggestion requests per run. Failed/interrupted requests are not automatically retried. Turn off consent to cancel queued work. Refresh suggestions to read results. AI questions never change tax figures or automatically award deductions/credits.

Super admins can generate six-year tax preparation and amendment products in Marketplace administration. Editable starter prices are $49.00 USD for preparation access and $79.00 USD for amendment access, per account/year. These are operator defaults, not researched market prices or official filing fees. Reruns preserve edited prices unless overwrite is explicitly selected. Products, currencies, descriptions, publication, coupons, users, workspaces, provider keys, gateways, fulfillment and platform deployment are managed through the existing super admin console. Tax-only amendment creation uses a separate tax_amendment_YEAR service.

Deploy the complete production marketplace stack with:
```bash
cd /root/DOBHRAP-oob
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/production-marketplace-oob.yml
```
This imports deployment, GUI/key provisioning, six-year readiness, migrations and product seeding. It publishes new starter offers, preserves existing edits and checks live merchant accounts/webhook signing for published settlement currencies. Missing live credentials or controls cause a clear readiness failure after the app and products are deployed. Coupons remain usable. To deploy offers in coupon-only/test mode, explicitly pass `-e marketplace_require_live_checkout=false`. Set `tax_preparation_price_usd`, `tax_amendment_price_usd`, `tax_publish_products` or `tax_overwrite_product_prices` to override seed defaults.

`ansible/tax-years-oob.yml` deploys and verifies the six-year GUI/API and saves `/var/log/oob-tax-years-readiness.json`. Passing `-e tax_require_filing=true` deliberately fails unless complete filing capability exists; no tax records are transmitted. Individual IRS electronic filing does not cover every old year. A validated full return package, eligible year/method, taxpayer signature/authorization and an authorized provider are still required. Production merchant readiness is saved in `/var/log/oob-marketplace-production-readiness.json`; a real completed checkout remains necessary to verify end-to-end payment delivery.


### Super admin commerce management

The super admin console and Commerce administration navigation now include a commerce dashboard, product/service pricing and publication, prepaid subscription plans and lifecycle management, payment gateway readiness, store identity/purchase availability, orders, fulfillment and coupons. Plans retain their purchased term on existing orders and expire or cancel service access. These are prepaid fixed terms with explicit new purchases for renewal, **not automatic recurring billing**. See `docs/USER-MANUAL.md` for operation and settlement limitations. Existing deployment playbooks migrate the catalog automatically.

## Watchdog events and super-admin reporting

Run `ansible-playbook -i 'dobhrap,' -c local ansible/watchdog-gui-oob.yml` after pulling this release on the hosting server. This deploys the GUI/API then installs the watchdog timer and its separate SQLite event database. The watchdog runs every minute, checks application identity, completed setup and anonymous session responses, and attempts bounded web-service restarts. It does not reset databases or retry financial jobs.

Open **Super admin → Watchdog events & reports** for the latest checks, stale-report detection, 24-hour event totals, the latest 200 events, manual refresh, automatic refresh while open and a JSON download of the displayed report. Events retain 90 days. `/api/platform/watchdog` permits GET only and requires a platform super administrator; ordinary tenant administrators cannot read reports. `/var/lib/oob-watchdog/events.db` is root-owned with read-only access for the application group. No credentials, response bodies or journal logs are stored in reports. Collection continues independently during business-database failures, but signing into the GUI still requires the business database. Server operators can use `journalctl -u oob-watchdog.service` during an outage. Persistent faults require operator repair.

### Prepare tax records for clients
Open Tax returns and create a separate draft for each client (registered or guest). In the draft, use **Client record request** to enter the client name/email, add custom checklist items and create a private upload link. Copy and deliver the link privately. Links expire after 30 days; replacement or revocation disables the earlier link. Clients do not need an account and must consent before uploading or marking a record not applicable. The baseline checklist covers identity, household, income, business/rental, deductions, education, insurance, payments and prior returns; applicability must be reviewed for each taxpayer.

Uploads use the existing encrypted PDF/PNG/JPEG document storage and limits (2 MB/file, 20 files and 12 MB per preparation). They attach directly to the selected draft's Documents slide. **Profile · Tax notifications** refreshes each minute and opens the preparation list, where record activity can be marked read and reviewed. The link grants submission access, not access to download existing records or edit the interview. The stored email identifies the client; no invitation email is sent, and no existing account records are shared automatically. Review uploaded originals and enter verified amounts into the interview; uploads do not automatically populate tax amounts or enable IRS transmission.

### Signed client agreements and QR invitations
In each preparation, **Client record request & agreement** now collects the client name/email, preparer name, self-reported PTIN (`P` plus eight digits), an agreed USD service fee, and the preparer's percentage share of that fee. Percentages and fees accept at most two decimals. The percentage is explicitly a service-fee allocation, never a percentage of a refund or tax savings; it records terms and does not collect payment. PTIN syntax checks do not verify credentials or identity.

Preview the generated engagement/record-sharing agreement, then create the invitation. **Copy URL**, **Share invitation**, and **Download QR invitation** provide the same private 30-day capability link. QR generation happens locally on the server using pinned `qrcode`, with no external QR service. Save the URL/PNG when created: the bearer token is not recoverable later. Share opens the device's share sheet and sends nothing until the operator chooses a destination and confirms. The canonical invitation origin is `https://olamideolatayobello.com`.

Clients must review the exact agreement, enter their full name, confirm acceptance, electronic signing intent and authority, and select **Sign agreement & unlock uploads**. The server blocks both uploads and not-applicable responses until the matching agreement fingerprint has a saved signature. Old invitations without agreements require replacement. Each agreement snapshots client/preparer/fee terms, version and SHA-256; encrypted signature receipts retain name, server UTC time and explicit confirmations. This records typed signing intent, not independently verified identity, IRS e-signature authentication, or a certified signature. Separate filing authorizations and any legally required use/disclosure consents remain necessary. No AI or marketing use is authorized by the generated engagement.

The client can download the agreement before signing and the signed receipt afterward. The preparer can reopen the draft and inspect agreement/signature history and download receipts. Replacing an invitation revokes its old link and requires a fresh signature; prior receipts remain retained. Signature events create profile notifications; uploaded encrypted document metadata records the matching agreement fingerprint. Changes to fees/identity/terms take effect only through a new invitation, not modification of a signed agreement. The existing Ansible repair/deployment installs the added dependency and migrates signature storage at startup.
