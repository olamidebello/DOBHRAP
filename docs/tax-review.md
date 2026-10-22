# Tax Analyst evidence and preparation review

On the hosting server (not the SIP server):

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
sudo ansible-playbook -i 'dobhrap,' -c local ansible/tax-review-oob.yml
```

The playbook uses the existing staged deployment/backup chain, then verifies the review schema in each real tenant backend and checks the served interfaces. Provider readiness and existing application deployment checks must pass. It does not run paid analysis or submit a return. A successful source commit alone does not deploy the running website.

Tax Analyst now provides guided upload/review/build actions, current-year selection, document search, attention filters, a preparation checklist, and an encrypted yearly review organizer. Review notes and missing-document requests are owner scoped. Closing a checklist item or request requires supporting notes. Follow-up dates are user entered; no email, calendar reminder, filing deadline calculation or outside communication is triggered.

The organizer checks possible duplicate transactions, source evidence, year/currency mismatches, unresolved classification, record/form overlap, missing entries and analysis failures. These are limited checks; a clean result is not proof of accuracy or eligibility. It retains source-linked deduction/income candidates and eligibility questions from the analysis report. It does not assume a purchase is deductible or a deposit is income.

After reviewing and saving records, build the selected year's preparation. Approved amounts continue through existing supported mappings. The compilation and individual draft also retain an immutable snapshot of the organizer, findings, source-linked benefit questions and notes. Individual preparation provides links to the matching interview sections. Federal workspace imports carry the same review snapshot. Recompile and reimport after changing source records or organizer notes; older snapshots remain unchanged. Unsupported or unapproved candidates do not become claimed deductions or credits.

The goal is to avoid missed lawful benefits while retaining evidence and eligibility review. The existing calculation engine remains limited: broad itemized deductions, credit phaseouts, all filing statuses, complete entity/state computations, elections and electronic filing are not implemented by this update. Existing supported projections retain their scope and blockers. No legal maximum refund is certified.

References used to design the question/source log:
- https://www.irs.gov/tax-professionals/eitc-central/due-diligence-requirements-for-knowledge-and-recordkeeping
- https://www.irs.gov/businesses/small-businesses-self-employed/recordkeeping

The organizer does not replace Form 8867, its required computations, or a preparer's professional due diligence.
