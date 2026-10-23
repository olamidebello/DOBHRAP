# Personal and Business registration

Sign in > **Create account — personal or business** opens `/register`. The account-type selector updates the explanation, business-name field, heading and submit button without losing email/password inputs. `/register` starts with Business; `/tax-services` starts with Personal; either page permits changing the selection.

| Choice | Required company name | Persisted account mode | Navigation |
| --- | --- | --- | --- |
| Personal | No | `tax_only` | Personal tax preparation, Tax Analyst, AI assistant, wallet, service payments and support |
| Business | Yes | `business` | Accounting, bookkeeping, business/employee workflows, tax services and permitted business modules |

The form POSTs to `/api/register`, then authenticates through `/api/login` and loads the account through `/api/me`. The backend validates `account_type` and rejects a conflicting `service_mode`. Existing clients using only `service_mode` remain compatible. Existing `tenants.service_mode` stores the choice, so no duplicate account-type column is introduced. Registration creates an administrator of that account's workspace, never a platform super administrator. Client-supplied role fields do not grant privileges. Existing ownership, workspace isolation, personal-service backend restrictions, CSRF and password validation continue to apply.

## Deploy

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
ansible-playbook -i 'dobhrap,' -c local ansible/account-types-oob.yml
```

The playbook stages committed source, installs pinned resources, runs release tests, initializes schemas, activates the application, verifies HTTPS and checks the selector and active database column. It does not create synthetic customer accounts on the live system. It does not require an OpenAI key/model to deploy registration.

## Verification coverage

API regression tests create both account types, check persisted modes/roles/access, and reject invalid or mismatched account types before allocating a workspace. Real Chromium mobile tests select both choices, submit registrations, verify authenticated landing pages and click wallet, marketplace, Tax Analyst and AI assistant navigation. An additional authenticated navigation test renders every visible super admin destination against the synthetic server (69 destinations in this release). Existing desktop/mobile smoke, client agreement/upload, attendance and password-recovery browser suites pass.

These checks verify the implemented navigation and supported workflows. External gateways, banking, payroll, AI and other provider-dependent services require their configured credentials and provider access. The test suite mocks provider activity and does not make paid AI requests, submit tax returns or initiate external payments. A rendered navigation destination does not establish that every optional service has been commissioned live.
