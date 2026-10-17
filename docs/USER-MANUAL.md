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
