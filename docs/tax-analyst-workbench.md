# Tax Analyst workbench and administration

This release extends the existing US tax-preparation application with local document/bookkeeping workflows inspired by the supplied feature inventories. It does not reproduce every feature of Dext, AutoEntry, QuickBooks or a professional tax-filing product.

## Deploy on the hosting server

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
sudo ansible-playbook -i 'dobhrap,' -c local ansible/tax-analyst-workbench-oob.yml
```

Run on `hosting`, not `sip`. The playbook imports the existing backup, immutable-release, migration and HTTPS checks; verifies the real tenant schemas, PDF/TIFF dependencies and served user/admin controls; and runs isolated synthetic bookkeeping/credit tests. It makes no paid document-analysis requests and submits no return. Existing application/provider readiness checks must pass. Running the playbook requires authenticated server access; a GitHub commit is not a live deployment.

## User navigation

Tax Analyst now offers **Upload**, **Review**, **Build worksheet**, **Tax review organizer**, **Bookkeeping, matching & expense tools**, and **Return diagnostics & readiness**.

The bookkeeping workbench provides tabs for invoice/receipt lines, supplier coding rules, bank transactions, supplier-statement entries, expense claims, mileage, commerce, suppliers/customers, and document questions. Records can be created, edited, reviewed, exported, or deleted when their workflow state permits. Originals and saved export snapshots are separate copies. Unsaved editing blocks navigation and destructive actions.

| Area | Implemented behavior | Boundaries |
|---|---|---|
| Capture | Web uploads, batches, drag/drop, mobile camera selection, private storage before processing | No background mobile GPS or standalone native mobile application |
| Formats | PDF, JPEG, PNG, bounded multi-page TIFF conversion, text DOCX, XLSX cell extraction | Legacy DOC must be converted to PDF; embedded/scanned DOCX images and macro/external-link workbooks are rejected; formulas are never evaluated |
| Extraction | Mode-specific totals, invoice lines, supplier statements and bank records using existing configured model | Results require review; totals service does not return a full transaction list; incomplete/invalid line extraction releases reserved credits |
| Invoice lines | Source, date, party, reference, quantity, unit price, gross amount, tax component, currency, category, account/tax labels, project, SKU, payment method | Tax codes are entered labels, not extracted rates or eligibility determinations |
| Rules | Reviewed supplier/description rules, preview, explicit application | No unattended posting or automatic approval; application returns a line to draft |
| Splits/merges | Gross/tax conservation; compatible sources/currencies/coding; superseded originals retained | Matched lines and lines already sent to tax intake cannot be transformed |
| Matching | Bank-to-reviewed-line matching by exact currency, flow and total; supplier entries also require supplier/reference match; unmatching | No automatic exchange conversion; local matching does not update a bank or accounting platform |
| Expense claims | Source receipt, assigned administrator, submission, independent approval/rejection and decision notes; scoped receipt download | Self-approval prohibited; approval does not initiate reimbursement |
| Mileage | Dates, origin/destination, distance/unit, vehicle, business purpose and optional supporting document | No GPS routing or automatic mileage-deduction calculation |
| Commerce | Itemized manual/CSV sales/refunds, SKU, tax, fee and shipping fields; currency-separated recorded summaries | No live ecommerce/store connection or revenue-recognition/tax engine |
| Data health | Missing sources, unclassified lines, possible duplicates, line arithmetic, unmatched bank/supplier entries, simple completeness score | Local equal-weight score is not a tax-compliance certificate or Dext proprietary score |
| Import/export | Typed CSV templates, bounded atomic imports, exact-row duplicate skipping, reviewed-only snapshots and safe CSV downloads | No live accounting publishing, chart-of-accounts synchronization, or unattended exports |
| Tax handoff | Reviewed lines become unapproved source-linked tax intake; repeat handoff does not duplicate the same line | Tax eligibility, business use and receipt/statement/form overlap must still be reviewed before compilation |
| Diagnostics | Stable codes, severity, source/form/section references, missing fields, invoice/statement arithmetic, refreshed saved-return checks, review notes | Critical checks cannot be acknowledged away; state rules and IRS/state e-file business-rule validation are not implemented |
| Correction navigation | Open a source document or related individual interview section; highlight the missing field when identified; federal-workspace navigation | Federal workspace input is opened at the workspace level |
| Readiness | Explicit federal/state/transmission blockers and signature/authorization limitation | No ready-to-file claim, submission, acknowledgment retrieval, rejection-code feed or resubmission connector |
| Questions and review history | Private document question/answer/source records, existing missing-document requests, encrypted notes and metadata audit events | No email, WhatsApp or chat message is sent by these records |
| External services | Clear connection status for email/WhatsApp intake, supplier fetching, live bank feeds, accounting sync, commerce connectors and regional/payment products | These adapters are not installed by this release; no credentials or third-party authorization are fabricated |

## Credit pricing

One previously purchased Tax Analyst session remains one credit. Existing balances, order amounts and old document reservations are preserved. New uploads get a server-derived processing quote. Existing uploads without a processing quote keep the legacy one-credit behavior.

| Processing | Default credit usage |
|---|---:|
| Invoice/receipt totals | 1 |
| Invoice/receipt line items | 2 |
| Supplier statement | 2 |
| Bank statement | 3 per verified PDF page |

The USD price per new credit retains the existing configured product price (previous default $5). Super Admin can change this price and each multiplier; this is the platform's pricing, not an AutoEntry subscription price. Bank page count comes from the server PDF parser; caller-supplied page counts are ignored. The confirmed credit count/rate revision is checked on upload and then saved with the document. Price changes do not reprice existing document quotes. Buying a single credit remains possible through the marketplace or the inline balance-purchase button; credit packs/subscription allowances are not implemented.

New UI uploads can be stored privately before credits are bought. Analysis requires the complete quoted number of prepaid credits, reserved atomically. Insufficient credits do not invoke the provider. Failure releases every reserved credit. Successful processing consumes them once. Concurrent requests cannot share the same credit. No payment card is silently charged, and no cash withdrawal is created. Super admin operational exemption is retained.

## Super admin navigation

**Super admin → Tax analyst management → Workbench modules, limits & workspace controls** provides:

- Enable/pause bookkeeping, rules, imports, exports, expense approval, mileage, commerce and diagnostics.
- Set yearly item limits and import/export batch limits.
- Allow supported processing modes and file formats.
- Pause new work in selected workspaces.
- Inspect schema readiness and aggregate kind/state counts, without taxpayer descriptions, amounts or document contents.
- Manage base USD credit pricing and per-mode multipliers; preserve old quotes and paid credits.
- Use existing provider/model, user/workspace access, wallet credits, payment gateway, worker and queue controls.

All switches are enforced in the backend. Disabling a feature does not destroy user records. Users retain original-document access and existing export downloads; queued/running provider activity follows the existing worker controls. A provider request already in progress may complete. Changing a policy does not grant e-file capability.

## Security and verification

Bookkeeping records, exports, review notes and diagnostic acknowledgments are encrypted using the existing persistent application key. Public feature/pricing policies contain no taxpayer data. Owner checks, tenant separation, CSRF handling, optimistic revisions, enum/date/amount validation, import limits and metadata audit entries apply. Expense reviewers receive receipt access only after the owner explicitly assigns and submits a claim to that administrator in the same workspace.

Feature inspiration for transaction rules and reconciliation: [Intuit bank rules](https://quickbooks.intuit.com/learn-support/en-us/help-article/banking/set-bank-rules-categorize-online-banking-online/L0mjJl0nD_US_en_US) and [Intuit reconciliation](https://quickbooks.intuit.com/learn-support/en-us/help-article/statement-reconciliation/reconcile-account-quickbooks-online/L3XzsllsK_US_en_US). The Dext, AutoEntry and diagnostic inventories were supplied in the request. No vendor affiliation or complete feature parity is claimed.

## Slow PyPI connections and offline installation

The password-recovery, normal deployment and MySQL staging installers use a 120-second pip socket timeout, five connection retries, preferred wheels, and a shared pip cache at `/var/cache/dobhrap/pip`. Pins and HTTPS verification remain enforced. Override with `-e dobhrap_pip_timeout=180 -e dobhrap_pip_retries=8` if necessary. A timeout followed by “from versions: none” does not establish that the pinned package is unavailable; inspect the preceding network error.

If the hosting server cannot reach PyPI at all, prepare a complete wheel directory on a connected machine matching the server's Python version, OS and architecture:

```bash
python3 -m pip download --only-binary=:all: -r requirements.txt -d wheels
```

Transfer that directory to `/opt/dobhrap-wheels` on hosting, then add these arguments to the deployment command:

```bash
-e dobhrap_pip_offline=true -e dobhrap_pip_find_links=/opt/dobhrap-wheels
```

Offline installation fails if any pinned requirement or transitive dependency is missing. It never silently falls back to the network. A staged dependency-install failure occurs before the active-release switch; rerun the playbook after restoring connectivity or supplying wheels.
