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

**Compile yearly worksheet / build 2026 preparation** includes approved, classified, in-year USD tax records and excludes personal/transfers/unapproved entries. No currency conversion or tax eligibility decision is applied. Each changed compilation creates a new snapshot and, for 2026, a new private preparation draft. An identical compilation reopens the existing snapshot. Open the 2026 preparation list and finish missing taxpayer, household, business, withholding, deduction and credit information; reconcile consolidated business intake by activity. Other years produce JSON worksheets only. The result is not an official tax return or filing package.

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
