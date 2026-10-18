# OOB Business Suite User Manual

## Language, currency and time zone preferences

Open Language & currency to select a CLDR locale, currency code and time zone. Core navigation has translations in English, Spanish, French, Arabic, Portuguese, German, Chinese, Hindi, Yoruba, Hausa, Igbo and Swahili. Other strings and locales use English fallback. Super administrators can publish plain-text translation entries. Locale formatting uses the currency’s decimal precision. The current ledger remains USD; choosing another display currency does not convert stored books. Dated reference rates can show labelled display estimates. Missing or stale rates leave USD amounts unchanged. Payment gateways still restrict supported settlement currencies.

## Setup, registration and sign-in

The operator deploys repair-oob.yml. Open /setup and use the private server setup token to create the first super administrator. Setup closes after creation. Register a new business at /register; registration creates a separate workspace and its administrator. Sign in with your email and password. Use Sign out on shared devices.

## Workspaces, roles and navigation

The super administrator manages workspaces and platform settings. Workspace administrators manage their own users and provider connections. Editors maintain business records; viewers read permitted pages. Use navigation search, bookmarks, Back, Home, Refresh and Print. Suspended workspaces cannot sign in or process scheduled operations.

## Customers, vendors and operational records

Open a module, choose New record, fill the fields, and Save record. Lists support search, sorting, pagination, View, Edit, Duplicate and Export CSV. General records are operational data. They do not post accounting entries automatically. Do not enter passwords, SSNs or payment-card data in general fields.

## Accounting, journals and financial reports

Balanced journals affect cash, income, expenses and financial statements. Record lists alone do not. Open Journals to post balanced debit/credit lines. Reports show trial balance and audit; Financial statements show posted profit/loss and balance sheet. Review bank imports before posting them to avoid duplicate ledger entries.

## Bank consent and automatic imports

An administrator opens Bank connections, checks consent, then connects with Plaid. Bank login and MFA happen in Plaid or the bank. Imports require configured credentials and user authorization. Automatic imports poll every 15 minutes; the bank determines data availability. Reconnect handles expired authorization. Pause stops future scheduled imports. Disconnect revokes the connection. PDF statements need separate consent, supported banks and Plaid Statements access. CSV is a fallback.

## Payroll, tax and approvals

Gross pay worksheet calculates hours times rate only. Provider payroll requires onboarding and credentials. Financial workflows require a second administrator to approve. Submitted means the provider received a request, not that funds were paid or a tax return accepted. Uncertain jobs require provider-console reconciliation. Tax organizer stores return information; the ordinary-income estimate is not a complete tax return.

## Marketplace purchases and fulfillment

Browse Service marketplace and choose a supported gateway. Prices are stored on the server. Checkout occurs at Stripe or Paystack. A return URL never confirms payment. Marketplace orders allows server-side verification. Confirmed payments create one purchased-service record and fulfillment entry. Test purchases stay marked test. Staff still deliver human services. Refunds and disputes require merchant-console reconciliation.

## Super admin provisioning and provider keys

Open Provider provisioning & keys. Confirm your administrator password to save, disable or test keys. Blank key inputs preserve saved values; Disable stores an empty override. Saved values are encrypted and never returned. GUI settings override server environment settings and apply to web and background workers without restarting. Live operations require an explicit confirmation. Merchant approval and provider key creation remain with the provider.

## Install, commission and manage deployment

Open Deployment & commissioning. The restricted management broker offers Verify, Backup, Deploy and Commission using fixed root-owned code. It cannot run arbitrary shell commands from the GUI. The server operator updates the repository and runs repair-oob.yml to install updated source. Back up the persistent encryption key separately from database snapshots.

## Tickets, AI assistance and escalation

Open Support center, describe the issue and choose a priority. Never include passwords, API keys, SSNs or card details. Opt into AI assistance only if you agree to share the ticket conversation with OpenAI. AI replies are labelled and can be wrong; they cannot change accounts, keys, payments or deployments. Human escalation cancels queued AI work. Replies, ticket state and overdue escalation are tracked. Workspace admins see workspace tickets; the platform super administrator sees all.

## Automation integrations

Automation runs through fixed scheduled workers: recurring records, approved jobs, bank imports, payment confirmation and support jobs. Super admin can enable AI auto-replies after per-ticket consent. Open tickets escalate when overdue. An optional inbound support endpoint accepts a separately configured bearer token and creates a ticket for an active workspace; it never runs arbitrary commands. No outbound email or chat messages are sent by this support integration.

## Mobile downloads and privacy

Open Mobile downloads for the installable web app or available Android preview. Provider login may require the normal browser. The service worker caches static assets only, never authenticated business APIs. Lock your device and sign out when using another person’s phone.


## 2026 tax preparation and record-assisted entry
Open **Tax → Tax preparation → 2026 Tax Return** to create a private, encrypted preparation worksheet. Continue through the slides or swipe horizontally; save and resume on another device. Supporting PDF/images are stored encrypted, but their contents are not automatically extracted. Income CSV imports append entries and require duplicate checks.

On Review, choose **Preview workspace income and expense records**. Only workspace administrators can import business records. Select records, confirm their tax year and ownership, and approve import. Source IDs prevent repeated imports of the same business records; manually entered or CSV amounts can still overlap. Imported expenses are intake entries, not automatically deductible amounts. Review and consolidate them.

Super admins can configure an OpenAI key, tax AI model and the explicit tax AI enable switch in the provider console. Each user must consent before requesting an AI opportunity review. Only categories and totals are sent; structured identifiers, names, addresses, notes and uploaded documents are excluded. Suggestions are unverified questions about possible deductions and credits, not eligibility decisions or refund computations. Requests are limited to one per draft per five minutes and twenty per user daily.

The interview exports an identification-masked preparation JSON and printable worksheet, not an official return. Other personal details remain in the owner’s export. Document downloads retain original contents. A limited ordinary-income estimate is available only for supported simple cases; credits, state taxes, capital gains, self-employment and special circumstances require additional calculations and professional review. No maximum refund, complete tax liability, signature, IRS transmission or filing acceptance is provided.


## Tax analyst: statements and receipts
Under the 2026 Tax Return navigation select **Tax analyst**. Choose the actual tax year and upload PDF, PNG or JPEG files up to 2 MB each. Original files and extracted records are encrypted and accessible only to their owner in that workspace. Up to one hundred documents / 100 MB per owner are supported.

Enable automatic analysis after upload or press Analyze later. You must consent to sending the **full original document** to OpenAI; redact unnecessary identifiers before uploading. This differs from the redacted summary-only opportunity review. Super admins configure `TAX_ANALYST_MODEL` (or `TAX_AI_MODEL`) and `DOBHRAP_ENABLE_TAX_ANALYST` in Provider provisioning & keys. Choose a model supporting the uploaded document type. Analysis is limited to one hundred requests per user daily; failed requests are not automatically retried. Split lengthy statements if output is incomplete. An interrupted request can be recovered after ten minutes.

AI creates unapproved proposed records. Open Review / edit records, verify dates, amounts, currency and source references, choose income/expense/transfer/personal classifications and categories, and set business-use percentages for business expenses. Add missing records manually or remove incorrect entries. Save before leaving. Approve only records you checked against the source. Credit deposits, transfers, loans and refunds require careful classification; net payroll deposits do not establish W-2 wages or withholding. Receipt totals can overlap bank transactions. Exact matching approved date/amount/type/description combinations are blocked as possible duplicates, but other overlaps require your review.

**Compile yearly worksheet / build 2026 preparation** includes approved, classified, in-year USD tax records and excludes personal/transfers/unapproved entries. No currency conversion or tax eligibility decision is applied. Each changed compilation creates a new snapshot and, for each supported year, a new private preparation draft. An identical compilation reopens the existing snapshot. Open the 2026 preparation list and finish missing taxpayer, household, business, withholding, deduction and credit information; reconcile consolidated business intake by activity. All six years support intake drafts; complete year-specific tax calculation is not implemented. The result is not an official tax return or filing package.

Download originals or compilation JSON as needed. Delete original/current records, compilation snapshots and guided preparation drafts separately; removing one does not erase the other copies or previous backups. Downloads contain financial data and may contain identifiers retained in source documents.

## Personal tax-only accounts and payment
Use **Tax services only — no business registration** from Sign in, or visit `/tax-services`. Register with email and matching passwords; no company name is requested. This account offers tax preparation, Tax analyst, tax payments, language settings, manual and support. Business accounting, payroll, banking integrations, administration and business APIs are blocked.

Upload and review analyst records first, then choose **Tax services & payment → Choose a tax-year service & pay**. A super admin must publish an offer with service code `tax_preparation_2026` (or the chosen year), its price and currency, and configure the matching live gateway. The account owner must complete hosted checkout and obtain server verification. Only fulfilled live payments with an active service unlock building/exporting that year. Pending, test and suspended services do not qualify. An unchanged compilation is reused; changed records create a new draft. This fee grants preparation access for that account/year, not an IRS filing entitlement or guarantee.


## Full-service coupons
Super administrators open **Platform → Coupon management**. Create a campaign label, enter a code or generate one, set a future expiry, total redemption limit and per-user limit, and optionally restrict the coupon to a service code and account email. Codes cover the full price of one eligible service per redemption. These vouchers do not support partial discounts, reusable monetary balances or cash change. Generated codes appear once; only a hash and last four characters are stored. Keep the issued code to share with the intended user.

Users open the marketplace, select an eligible service, enter the coupon and press **Pay with coupon**. The server atomically checks restrictions and remaining uses, records a zero-cash fulfilled order and activates the service. Coupons for `tax_preparation_YEAR` satisfy that account owner’s tax-year preparation payment requirement. No gateway charge is made. Repeated submission of the same purchase request does not consume an additional redemption.

The super admin can enable/disable future use and inspect redemption counts and audit records. Disabling or expiring a coupon does not cancel services already redeemed. Suspend the purchased service separately to revoke its tax preparation access. Publishing a coupon does not enable IRS filing or imply tax calculations beyond the supported preparation worksheet.


### Upload a complete tax document collection
Tax analyst accepts multiple PDF, PNG and JPEG uploads, up to 2 MB each and 100 files / 100 MB per owner. Choose Auto or identify W-2, 1099-INT/DIV/NEC/MISC/K/R/B, SSA-1099, 1098/T/E, 1095-A, K-1, prior-year returns, estimated payments, charity evidence, business records or Other tax document. This list describes intake categories, not complete tax calculation support. Export Word/Excel or other files to PDF before upload. Use separate files for separate tax forms and redact unnecessary identifiers.

Select full-document AI consent and Analyze automatically after upload, or use Analyze pending documents after saving the collection. The existing one-hundred-analysis-per-user daily limit applies; uploaded files remain saved when analysis is disabled, fails or reaches the limit. Review batch results and retry pending documents explicitly after resolving the issue. No automatic paid retries occur.

AI separates transaction entries from tax-form box fields. Edit form name, box, label, value, currency, tax year and source reference, then approve verified fields. Unknown years must be confirmed, and fields from a prior-year return must not be approved as current-year amounts. AI is instructed to omit personal identifiers; review its output and remove any unnecessary identifiers. Review originals for missing or incorrect amounts.

Compilation automatically maps approved USD W-2 boxes 1/2, 1099-INT boxes 1/4 and 1099-DIV boxes 1a/1b/4 into the supported income interview. These box mappings use the IRS forms at https://www.irs.gov/pub/irs-pdf/fw2.pdf, https://www.irs.gov/pub/irs-pdf/f1099int.pdf and https://www.irs.gov/pub/irs-pdf/f1099div.pdf. Other approved fields are preserved in the compilation JSON for manual preparation; they do not automatically compute credits, itemized deductions, retirement taxability, capital gains, business tax or state returns. Avoid approving both bank deposits and tax-form amounts for the same income.


The upload form includes a document-type dropdown and an optional custom record-type text box. Custom text takes priority over the dropdown. Automatic analysis is selected by default when AI is configured; users must give full-document sharing consent or deselect it for private storage only. Select files and, if needed, press Upload selected documents after granting consent. Uploads are grouped by year and selected/detected type. Exact monetary summaries separate currency, income/expense/transfer classifications, approval status and supported tax boxes; they never add wages to withholding or different currencies. When Auto detects a single tax form, that form becomes the document group. Unverified totals are labeled unreviewed. Summaries are not tax or refund computations.


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


## Super administrator commerce controls

Sign in with the `super_admin` role. The **Commerce administration** navigation and the **Super admin** console provide:

- **Commerce dashboard:** published offers, recent orders, fulfillment, prepaid terms and verified live gross totals separated by currency. Totals cover at most the latest 500 orders and exclude refunds, fees, disputes, coupons and test orders.
- **Marketplace administration:** create/edit/publish/archive products and service offers, set prices and service codes, and generate editable tax-year starter offers.
- **Subscription plans:** create/edit/publish/archive prepaid plans with a fixed 1–366 day term. Prices are minor units (4900 means USD 49.00). Plans use existing verified Stripe/Paystack checkout or eligible full-service coupons. Existing orders retain their purchased term when a plan changes. Tax-year access remains a one-time offer.
- **Subscription management:** search/export subscriptions across workspaces and cancel service access immediately. Customers can view and cancel their own terms under Purchased services. Cancellation suspends service access and does not issue a refund. Each additional purchase starts a separate term at fulfillment; terms do not automatically stack. There are no automatic recurring charges or scheduled renewals. Purchased plans create fulfillment records; they do not unlock unrelated application modules.
- **Payment gateways:** inspect test/live readiness, signing-key readiness and last signed events. Open Provider provisioning & keys to save encrypted keys, test merchant connections, and provision Stripe webhooks after confirming the current administrator password. Refunds/disputes remain merchant-dashboard operations.
- **Store settings:** change store name, description and support email; pause or resume new gateway purchases and coupon redemptions. Existing payment verification and services continue when purchases are paused. Preview the store from this page.
- **Purchased services:** set fulfillment to new, in progress, completed or suspended. Expired/cancelled subscription terms cannot be restored through fulfillment controls.

Terms are checked on authenticated requests and by the marketplace scheduler. The database migration preserves existing offers, orders, services and credentials. Deploy through the existing repair/provisioning playbooks; no separate manual SQL migration is needed.


### Multiple documents and individual classifications

In Tax analyst or a preparation's Documents and import review slide, select multiple PDF/PNG/JPEG files. A queue lists each filename with its own document-type dropdown and optional custom record type. Defaults apply to newly selected files; edit individual rows for mixed batches. Custom record types override the dropdown. Remove unwanted files before clicking **Upload selected documents**. Files upload sequentially; successful files leave the queue, while failed files remain with an error for correction/retry. Maximum file size is 2 MB. Existing owner/return storage limits still apply. Pending uploads block navigation until uploaded or removed.

Tax analyst can analyze uploaded files when configured and the user explicitly consents. Direct uploads to preparation store documents and their classifications privately; they do not automatically extract figures. Choose Tax analyst for extraction and review/approve its results before compilation.

## Prepare for a client: agreement, invitation and uploads
Create a separate Tax returns draft for each client. Open **Client record request & agreement**, enter the client and preparer details, optional PTIN, agreed USD service fee and the preparer's percentage share of that fee, then add custom requested records. The percentage is a share of the agreed service fee, not a share of any refund or tax savings. PTIN entries are self-reported, not verified by the platform.

Choose **Preview generated agreement** to review or download the engagement. **Create invitation URL & QR** saves its terms and generates a private link and downloadable PNG QR code. Copy the link or use your device's share sheet to send it privately. Save the URL or QR before leaving; a replacement invalidates the previous invitation. Invitations expire after 30 days and can be revoked.

The client opens the URL or scans the QR, reviews the agreement, enters their full name, confirms agreement acceptance, electronic signing intent and authority, and signs. Upload controls appear only after a successful saved signature. The client can download a signed receipt and return using the same valid invitation to upload more records. Old invitations without an agreement require a new invitation. Uploaded documents appear in that preparation's Documents slide; review them and enter verified figures in the interview.

**Profile · Tax notifications** reports agreement signatures and record activity. Reopen the draft for agreement/signature history and downloadable receipts. Signed terms cannot be edited: create a replacement invitation and obtain a new signature for changed fees or details. These typed signatures do not independently authenticate identity or authorize IRS filing. Separate required filing and tax-information-use authorizations still apply. The generated agreement does not authorize unrelated disclosure, marketing, AI analysis, payment collection or refund redirection.

### Custom document request fields
In the client agreement form, select **Add document request** for each custom field (up to 20). Enter a unique document name and an optional description with upload instructions, then create the invitation. Use **Remove request** to remove an unwanted field before creating the invitation. Saved fields and descriptions reload when you reopen the draft. Existing invitations remain unchanged until you issue a replacement invitation.

After signing, the client sees each request name, its description, a **Choose files** button, selected filenames, **Upload selected**, and **Not applicable**. PDFs, JPGs and PNGs attach to the matching preparation with their request name, saved description and agreement reference. Older requests containing only names continue to work. Signature requirements and existing upload limits still apply.

## Employee clock and employer payroll statements
1. Open **People & payroll → Employee clock & payroll statements**. Save the employer name/address and IANA workweek time zone before recording time. The time zone is fixed after the first shift.
2. Create a site. Choose location requirement, latitude/longitude, radius, GPS uncertainty limit, allowed weekdays and clock-in hours. **Use my current location** can fill the coordinates. Equal start/end times permit all day. Disable a site by editing it and clearing Active.
3. Add an employee or contractor with name, email, phone, role and hourly USD rate. Optionally enroll an SSN for SSN+PIN access, or use the generated employee ID. Save, copy the employee portal URL and download/share its QR. Deliver the initial PIN separately and privately; it is shown only once. **Reset PIN** generates a replacement and revokes employee sessions. Edit a worker to update profile/rate or remove SSN enrollment. Suspend workers only after closing/correcting open shifts.
4. Workers open **Employee / contractor clock** from the public landing page or their invitation. Enter company workspace ID, employee ID (or enrolled SSN) and PIN. Sign-in does not clock in. Select the work site, check location/schedule if needed, then choose **Clock in**. Choose **Clock out** when stopping work, including before an unpaid break; clock in again when returning. **Sign out of portal** only ends the login session. Workers can review completed timesheets, draft weekly gross earnings, change their PIN and download/print published statements.
5. Employers review the latest 500 shifts, download timesheet CSV, add verified missing shifts and correct timestamps with reasons. Correction history preserves original times. Completed shifts also appear in the ordinary Time sheets module. The clock never automatically fabricates a forgotten clock-out.
6. Select a Monday and one to four workweeks, then generate a payroll draft. This automatically totals recorded completed hours and supported gross earnings. Resolve open/overlong shifts and unsupported multiple-rate weeks first. After the whole period ends, enter independently verified federal/state/FICA/other deductions for every worker, confirm the review, and publish statements. Employees can then download a text statement or use **View / print paystub** to print/save PDF. Publishing does not transfer money or remit taxes. Published periods are locked; corrections require a separate payroll adjustment workflow.
7. A super administrator can open **Workforce platform controls**, suspend new clock access globally, and open each business workspace to administer workers, PINs, sites, shifts and payroll records. Tax-only accounts cannot use employer clocks.

Supported draft arithmetic is hourly USD pay with employee overtime after 40 hours per workweek at 1.5 times the single hourly rate; contractors use straight time. This does not cover every jurisdiction, classification, exemption, daily overtime, bonuses, benefits or payroll tax rule. Use a qualified payroll calculation/provider for those requirements. A generated statement is an employer-recorded earnings statement, not payment confirmation or certified jurisdiction-specific paystub. Browser location can be spoofed; biodata and optional SSN+PIN are not biometric identity verification. No full SSN is retained and no PIN is included in the QR code.
