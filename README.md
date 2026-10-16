# DOBHRAP Business Suite

A self-hosted initial implementation for accounting operations, people records, and tax-preparation information. Python 3 standard library, SQLite, responsive browser interface, systemd, nginx, and Ansible. This is not a feature-complete replacement for QuickBooks, TurboTax, or ADP.

## Implemented

- Session sign-in, scrypt password hashes, CSRF protection, administrator/editor/viewer roles, account creation, sign-out.
- Database-backed create, edit, list, and search screens for customers, vendors, products, invoices, bills, expenses, projects, employees, timesheets, leave, recruiting, benefits, performance goals, tax returns/documents/income/deductions, bank-review records, and tasks.
- Chart of accounts, immutable posted journal entries, balanced integer-cent journal validation, trial balance, CSV export, and write audit trail.
- Gross-pay preview using manually entered hours and rate.
- Dashboard, navigation, accessible labeled forms, responsive layouts, and validation feedback.
- Ansible installs prerequisites, application, private persistent database, restricted service account, nginx reverse proxy, HTTPS certificate and readiness checks.

## Local development

Python 3.11+ recommended. Set `DOBHRAP_ADMIN_EMAIL` and `DOBHRAP_ADMIN_PASSWORD` (14+ characters) in your environment, then run:

```bash
python3 app.py
```

Open http://127.0.0.1:8080. The first startup creates the administrator. Changing the environment password later does not change an existing account. Local cookies are HTTP compatible; production sets secure cookies. Do not expose the Python server directly; it binds to loopback.

```bash
python3 -m unittest discover -s tests -v
```

## Deploy

Install Ansible on your control machine. Clone this repository there, copy `ansible/inventory.example.ini` to an inventory outside the repository and set the target server. Target Debian/Ubuntu with SSH and privilege escalation. Point domain DNS to the server; ports 80/443 must be reachable for Certbot.

Create an Ansible Vault encrypted variable file outside the repository containing `admin_password`, `admin_email`, and `domain`. Use a strong unique password. Then run:

```bash
ansible-playbook -i /path/to/inventory.ini ansible/deploy.yml --ask-become-pass --ask-vault-pass -e @/path/to/encrypted-secrets.yml
```

The playbook copies this checkout to the server, starts the app and provisions HTTPS. It preserves an existing domain configuration to avoid overwriting Certbot changes. Review existing hosting configuration for conflicts before deployment. It does not create DNS records. Certificate provisioning fails explicitly if prerequisites are missing. A failed certificate step may leave HTTP available; secure login cookies require HTTPS.

## Accounting boundaries

Invoice, bill, expense and bank-review records are operational records only: they do not automatically post ledger entries. Post appropriate balanced entries through Journals. Record amounts are entered in currency units; journal amounts and report totals are integer cents. The current app is single-company and single-currency. Product quantities are editable records, not a stock-movement ledger. No payments are collected or sent.

## Requested capability coverage and remaining work

| Area | Current behavior | Remaining work |
|---|---|---|
| Navigation and dashboard | Module links, summaries, search, create/edit forms | Bookmarks, notifications, customization, global search |
| Sales and purchasing | Customer/vendor/invoice/bill/expense records | Line items, estimates, credits, receipts, statements, reminders, PDFs, recurring transactions, approvals, automatic posting |
| Banking | Manual bank-review records | Bank-provider connections, import, matching, categorization rules, reconciliation |
| Accounting | Seeded accounts, balanced journals, trial balance | Account maintenance, reversals, closing dates, P&L, balance sheet, cash flow, budgets, multicurrency, classes and locations |
| Inventory/projects | Basic item and project records | Stock ledger, COGS, purchase orders, valuation, barcode/warehouse/lot tracking, actual project costing |
| HR | Employees, leave, applicants, benefits and goals records | Employee self-service, approvals, accruals, recruiting workflows, onboarding/offboarding, learning and carrier feeds |
| Time/payroll | Time records and gross-pay worksheet | Clocking, schedules, overtime, deductions, jurisdiction tax tables, net pay, deposits, tax forms and filing |
| Tax preparation | Return metadata and income/deduction/document metadata | Tax engine, interview rules, actual document upload/OCR/import, forms, state calculations, review, signatures, IRS/state e-file, amendments |
| Integrations/AI | No external service calls | Provider credentials, verified connectors, webhooks, consent and authorization, AI assistance |
| Administration | Three roles and audit records | Password reset/MFA, per-module permissions, multi-company isolation, encryption key management, backup/restore automation, monitoring, disaster recovery |

Tax-document records store metadata only, not uploaded files. Do not enter SSNs, bank account credentials, medical records or tax documents into this initial version. No tax rates, legal conclusions or statutory compliance claims are built in. Additional engineering and verified jurisdiction-specific rules are required before live financial, payroll or tax operations.

## Operations

Database: `/var/lib/dobhrap/dobhrap.db`; service: `dobhrap`; secrets: `/etc/dobhrap.env`. Use `systemctl status dobhrap`, `journalctl -u dobhrap`, and `nginx -t` for diagnostics. Back up SQLite using its online backup API or stop the app before copying the database. A backup/restore automation is not yet included. The application is intended for one instance; scale-out and multi-tenant use require a different database and isolation design.
