# Manual cash-out

Deploy from the hosting server:

```sh
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
sudo ansible-playbook -i 'dobhrap,' -c local ansible/cashout-oob.yml
```

The installer tests the feature before switching releases, uses the existing database backup and migration workflow, verifies the active SQLite or MySQL backend, and verifies the served interface. It enables new requests on first installation and preserves subsequent administrator pauses. It does not authorize funds, send money or configure a bank-transfer provider.

Super Admin opens **Cash-out management**. First authorize a portion of an existing user balance backed by verified funds available for payout; record the funding source. Authorization adds no money. Existing manually granted promotional/store credit remains nonwithdrawable unless explicitly authorized. User purchases consume nonwithdrawable credit first and reduce remaining withdrawal eligibility when necessary. Currencies remain separate.

Users open **Cash out** from Marketplace navigation or Account balance. They see spendable and withdrawable balances, submit an amount and bank destination, view history and cancel pending requests. Submission removes the amount from spendable and withdrawable balances into a request hold. Rejection (pending or approved) or user cancellation (pending only) releases the hold once. Approval keeps the money held. Super Admin can view encrypted bank details on demand; each view is audited. Request lists never expose bank details.

After completing payment outside the application, Super Admin enters its reference and confirms completion. The final state is **payment_recorded**, an administrator assertion, not independently verified bank settlement. The app never initiates transfers. Do not record payment until it is complete; pending/approved holds must not be released after an external payment has been made. All money changes are atomic and requests use replay identifiers. Balances and request history are user scoped; control routes require Super Admin and mutation routes require CSRF protection.

Automatic bank transfers require a separate payout provider integration, settlement verification and reconciliation. No such integration is included here. Store credits, cash-out holds and releases appear in the wallet ledger; external payment references appear in request history and audit events.
