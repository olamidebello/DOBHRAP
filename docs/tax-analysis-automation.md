# Sequential AI document analysis

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
sudo ansible-playbook -i 'dobhrap,' -c local ansible/tax-analysis-automation-oob.yml
```

This deploys the app, migrates platform and tenant databases at startup, reuses the
saved OpenAI key and document model, and installs `oob-tax-analysis.timer`.
It does not create a key, rotate credentials or make a paid deployment test.
The preflight requires the worker environment files to match the live web service's
database backend and encryption context. Configure a document-capable Tax Analyst
model in Provider provisioning & keys if the existing model is missing.

Open **Tax preparation → Tax analyst**. Upload PDF/PNG/JPEG documents, select the
tax year, confirm authority and full-document AI consent, then enable **Queue
background analysis after upload** or select **Queue pending documents**. Consent
authorizes sending original document contents, including visible personal data,
to the configured OpenAI API and can incur provider charges. The browser may close
after queueing. **Cancel queued documents** cancels work not yet started; a running
request can finish. Use **Reload saved records** to check persisted progress.

The timer checks each minute and processes at most one document per invocation.
A file lock prevents overlapping background extraction workers. Owner/workspace
access, optimistic revisions, the existing 100-request daily cap and configured
provider settings are rechecked. Changed/deleted documents and inaccessible owners
cancel pending work. Failed or interrupted jobs are not retried automatically.
Manual per-document analysis/recovery remains available after review.

The AI is asked to inspect each page and relevant line in source order and retain
page/line or printed-box references. It reports unreadable or omitted material,
suggested grouping and deduction/credit eligibility questions. These are unverified
outputs, not proof that every line was read. Existing limits remain 2 MB per file,
100 documents/100 MB per owner, 150 extracted transactions and 200 tax fields per
document. Split long documents if incomplete. Do not upload unsupported formats.

**Review grouped lines & W-2 target** groups transactions by reviewed or suggested
category and form fields by form type, with source references, amounts and approval
status. Opportunity questions remain advisory. AI never approves entries or assigns
business-use percentages. Check originals, duplicates, year, currency and eligibility
before compiling approved records into a preparation draft. Full itemized deductions,
all credits and state returns are not implemented by this workflow.

The W-2 Box 2 subtotal includes only approved same-year USD fields; suspect duplicates
and unresolved entries are flagged. It is withholding, not a deduction or minimum
refund. On the preparation Review slide, the existing supported refund projection
compares its calculated result with entered W-2 withholding and shows the difference.
It never raises a refund, changes tax figures or invents deductions to reach that
comparison target. Additional taxes may make the refund smaller; credits and other
payments may make it larger. A complete validated return is still required.

```bash
sudo systemctl status oob-tax-analysis.timer
sudo journalctl -u oob-tax-analysis.service --since '15 minutes ago'
```

If an older worker fails with permission denied on
`/var/lib/dobhrap/tax-analysis.lock`, pull the latest source and run:

```bash
sudo ansible-playbook -i 'dobhrap,' -c local ansible/repair-tax-worker-oob.yml
```

This bounded repair uses a systemd-owned runtime directory at
`/run/oob-tax-analysis`, preserves database ownership, pauses the timer during
the update, refuses to interrupt running analysis, and processes at most one
existing consented queue item afterward. The worker logs only a processed count,
not document contents or credentials.

Sources: https://www.irs.gov/pub/irs-pdf/fw2.pdf and
https://www.irs.gov/pub/irs-pdf/f1040.pdf.

## No W-2 available

On the preparation Start slide, select **W-2 availability**. Choose `not_expected`
only when no wage income requiring a W-2 is expected. The supported projection
then uses verified federal withholding on entered income, estimated/extension
payments and prior-year applied credits as a comparison reference. Its refund
estimate remains payments minus supported calculated tax; it never applies a
fixed minimum or raises the result to equal payments. Refundable credits remain
outside this limited numerical engine and require qualified calculation.

Choose `expected_missing` if a W-2 is missing. The projection stays blocked until
wage/withholding records are reconciled. Request the form from the employer and
review IRS Form 4852 requirements if it cannot be obtained; this app does not
automatically prepare or validate that substitute form. Unknown missing-form
status also blocks a projection when no W-2 income has been entered. Unavailable
data are not inferred from bank deposits or replaced by a recommended refund.

IRS missing-form guidance: https://www.irs.gov/forms-pubs/about-form-4852.
