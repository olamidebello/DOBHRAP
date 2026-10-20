# Tax Analyst management, session purchases and federal return workspaces

Deploy on the existing hosting server:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
sudo ansible-playbook -i 'dobhrap,' -c local ansible/tax-filing-suite-oob.yml
```

The playbook uses the existing staged-release installer, live-backend backup and migrations, bounded analyst worker, official-reference refresh and provider configuration. It then checks the new tenant schemas and GUI resources and downloads pinned-year public official IRS PDFs into `/var/lib/oob-tax-forms`. Download availability, hashes and revision-review status are visible to Super Admin. A missing 2026 resource remains unavailable; the installer never substitutes a prior-year or draft form as a final form. Public resource fetching sends no taxpayer data and makes no paid AI request.

## User session purchase

The default marketplace offer is **Tax Analyst — one document session**, USD **$5.00**, service code `tax_analyst_session`. One verified live purchase covers one completed document extraction. A parsed response can contain no financial entries; users still must reconcile source coverage. A provider/parsing failure returns the session for an explicit retry. A session is not a timed login, unlimited document batch, tax-year preparation purchase or promise of a refund.

Users open **Tax analyst → Purchase a session** and pay from a sufficient USD account balance or through the existing USD-capable live Stripe checkout. External payments are verified under Marketplace orders; wallet purchases settle internally and activate immediately. Provider-side verification must match the original order amount, currency and reference. Test-mode payments, pending orders, browser redirects and coupons do not grant analyst sessions. A USD payment gateway must already be configured in live mode; the installer does not create merchant credentials or enable live payments. Editors may purchase their own analyst session, while other marketplace offers retain administrator purchase requirements.

Super administrators can manually grant general-purpose store credit under **User balances & manual credits**; see [wallet documentation](wallet.md).

Before a non-super-admin uploads a document or queues an analysis, the backend checks an unused session. Each actual analysis reserves a distinct paid order atomically before contacting OpenAI. It is consumed only after the result is saved; known extraction failures return the credit. Uploading or queueing multiple files with one session does not authorize multiple successful extractions: jobs that reach the worker without another available session fail without a provider call and show the purchase requirement. Buy sufficient sessions for a batch. Saved records, original downloads and reports remain accessible after a session is consumed.

Requests interrupted by a process stop keep their session reserved until the owner uses the existing interrupted-analysis recovery after ten minutes. Recovery releases that reservation without an automatic paid retry. Unknown outcomes must be reconciled; repeated queue timer runs never blindly retry paid work. Super administrators are exempt for platform operations, which is displayed in their Analyst GUI. They do not receive access to another owner's private return payload simply by opening management metadata.

## Super Admin controls

Open **Super admin → Tax analyst management** or the Platform navigation entry.

- Change the USD session price and publish/pause the offer. The $5 default is inserted only if the canonical offer is missing; deployment preserves subsequent administrator price changes.
- Review session usage and suspend/restore unused sessions. Used and running sessions cannot be reset through these controls. These actions do not issue payment-provider refunds.
- Pause new AI analysis, uploads, new queues, background work or return editing independently. An already-running provider request may finish.
- Set paid-attempt limits (1–100 per user / 24 hours), document limits (1–100) and file size limits (1 KB–2 MB).
- Enable 2025/2026 return years and Form 1040, 1065, 1120-S and 1120 workspaces.
- Review queue metadata and return counts across workspaces, cancel only unstarted jobs, inspect control audit history, and navigate to providers/models, workspaces/users, orders and payment gateways.

Policy and price edits use optimistic concurrency checks. Backend role authorization and CSRF validation apply even if UI controls are bypassed. Platform listings contain metadata, not taxpayer document contents, API keys or private case names. A suspended marketplace service also makes its remaining analyst session unusable.

## Federal return workspaces and actual calculation coverage

Open **Tax preparation → Federal return workspaces**. Each owner can create, reopen, edit, recalculate, import a matching-year approved analyst compilation, archive/restore, delete and export their own encrypted workspace. Imports replace financial inputs rather than accumulate repeated totals and reset review confirmations. Existing tax-only tax-year payment/coupon requirements also apply to creation, saving, importing and exporting these preparation workspaces; purchasing an analyst session does not purchase return preparation.

Both 2025 and 2026 are available for these families:

| Family | Implemented preparation | Not implemented |
| --- | --- | --- |
| Form 1040 | Financial intake, approved analyst import, Schedule C gross-profit/expense worksheet, regular Schedule SE worksheet with W-2 Social Security wage coordination and half-SE-tax deduction worksheet | Complete individual tax, QBI, credits, final IRS form population, tax-table validation, signature/filing package |
| Form 1065 | Entity financial intake, gross-profit worksheet, owner-share arithmetic, K/K-1 and reconciliation blockers | Actual distributive-share rules, partner basis/capital accounting, all K-1s, complete official return |
| Form 1120-S | Entity financial intake, owner-share arithmetic, shareholder/election/reconciliation checklist | Complete S-corporation tax, basis, K-1s and official return |
| Form 1120 | Entity financial intake and book-to-tax/tax/payment review blockers | Complete corporate tax, NOL/credit/election computation, Schedule J and official return |

Regular-method SE worksheets use 92.35% of net profit, the $400 net-earnings threshold, 12.4% Social Security up to the remaining wage base, and 2.9% Medicare, with half the calculated regular SE tax shown separately. Wage bases are $176,100 for 2025 and $184,500 for 2026. W-2 box 3 must be entered separately; box 1 is never silently used as Social Security wages. Clergy/church rules, railroad income, exemptions, optional methods, Additional Medicare tax and joint/multiple-person allocations require separate review. Losses, owner allocations and special deductions are never silently treated as final eligibility determinations.

Every new workspace currently has `filing_ready: false` and `transmission_available: false`. Administrator switches and review checkboxes cannot override that. Exports are marked **NOT-FOR-FILING**. This release builds the managed preparation workflows and bounded worksheets; it does **not** complete every official IRS form or produce a filing-ready return.

References: [Schedule SE](https://www.irs.gov/instructions/i1040sse), [SSA wage bases](https://www.ssa.gov/oact/cola/cbb.html), [Form 1065](https://www.irs.gov/forms-pubs/about-form-1065), [Form 1120-S](https://www.irs.gov/forms-pubs/about-form-1120-s), [Form 1120](https://www.irs.gov/forms-pubs/about-form-1120).
