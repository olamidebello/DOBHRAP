# Business profiles, SAM.gov and proposal preparation

Business workspaces have **Business development → Business profile & contracts**. Business administrators maintain a shared profile containing legal name, DBA, entity type, year founded, EIN, CAGE code, UEI, NAICS and product/service codes, address, website, primary/alternate contacts, certifications, capabilities, verified past performance, staffing, service regions and insurance/bonding information. Profile changes use revision checks; stale saves are rejected. The existing business-logo upload remains in Phone & PBX.

Profiles and saved proposal/opportunity snapshots are encrypted with the persistent application key. The EIN is masked in responses; a blank EIN preserves the stored value. Business administrators can edit the profile, viewers are read-only, and other workspaces cannot access its data. Identifiers and certifications are self-reported: formatting checks do not verify an IRS EIN, DLA CAGE registration, SAM registration, eligibility or a certification. The interface does not collect bank details.

## SAM.gov automatic configuration and super admin controls

Run the existing pull-and-deploy command on the application host. It deploys the new database tables, routes, JavaScript and navigation, then runs `ansible/configure-sam.py`. This reuses `SAM_API_KEY` in encrypted provider settings or imports a root-only `/root/dobhrap-sam-api-key` file (mode 0600). It makes one read-only public-opportunity API request to check connectivity and enables the application search policy only when that check succeeds. No key is printed. Provider checks consume SAM.gov quota, including commissioning checks.

**SAM.gov issues its own keys.** Obtain the key from your SAM.gov account's Account Details; this application cannot create a government account or mint a valid key. Save it under **Super admin → Provider provisioning & keys → Federal contract opportunities**, confirming the current administrator password. Blank secret inputs preserve an existing key. The commissioning script can use an existing server environment key too. Do not put a key in Git or chat.

**Super admin → SAM.gov provisioning & controls** includes key-presence status, a secure settings shortcut, a password-confirmed connection test, an enable/disable switch, a daily platform search cap, recent connection checks and 30 days of daily call counts. Policy saves reject stale revisions. The default search cap is 100 per UTC day; allowed settings are 1–1000. The government account's actual quota can be lower. Failed attempts count; explicit administrator connection tests are separate from that application search cap.

Customer searches default to the first saved NAICS code, with optional title keywords, posted-from/to dates and page number. The adapter uses the production public Opportunities API, `ncode`, `title`, required posted dates and pagination. Date windows are limited to 365 days, 25 results are fetched per page and pages are limited to 0–39. Workspaces wait 30 seconds between calls. Searches require an enabled policy and a key. Results are cached as tenant-scoped snapshots; view saved notices without another provider call. Source links are constructed on sam.gov, and provider description/attachment URLs are not fetched automatically. A search is not an exhaustive procurement feed or an eligibility determination. Check live notices, deadlines, amendments and attachments before bidding.

For deployment without mail/PBX commissioning, use:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
ansible-playbook -i 'dobhrap,' -c local ansible/business-contracts-oob.yml
```

This invokes the established application repair/build/test deployment before commissioning SAM access. It does not reset credentials, replace an administrator or transmit proposals.

## Proposals and AI options

Select a saved opportunity and click **Create proposal draft**. The local outline includes source reference, executive summary, technical approach, staffing/schedule, past performance, pricing placeholders and a compliance checklist. Edit, save, reopen, download as text, delete, or mark human-reviewed. Revision checks protect concurrent edits. The review marker is internal and does not submit or approve a government bid.

**Prepare AI proposal request** offers full draft, outline and compliance-checklist modes plus a box for pasted solicitation requirements. It prepares a prompt from the saved opportunity's title/source/notice ID and selected business capability facts. Dedicated EIN and contact fields are excluded; review all free text for sensitive information. The system does not retrieve full solicitation attachments and does not assert that the pasted requirements are complete.

The button opens the existing AI assistant with the prepared prompt. Users review the selected provider, data-sharing consent and maximum USD balance reservation before requesting generation. Existing configured OpenAI/Claude model access, verified token prices and the 30% markup apply. No new key is created, no silent fallback occurs and no provider is called just by preparing a prompt. After generation, **Save generated answer to proposal** stores the visible answer as a draft. Review unsupported assertions, evidence gaps, pricing, compliance and the live solicitation before marking it reviewed. No bid or certification is sent to SAM.gov.

## Resources

Root database tables: `business_profiles`, `business_opportunities`, `business_searches`, `business_proposals`, `business_sam_policy`, `business_sam_usage`. Routes: `/api/business/profile`, `opportunities`, `proposals`, `proposal-create`, `proposal-save`, `proposal-delete`, `proposal-prompt`, `sam-admin`. Frontend: `business-contracts.js`; backend: `business_contracts.py`. All routes require the existing authenticated workspace and CSRF controls. Admin key storage uses the existing encrypted `provider_settings` table.

Official API contract: https://open.gsa.gov/api/get-opportunities-public-api/ . Quotas and account permissions are controlled by SAM.gov.
