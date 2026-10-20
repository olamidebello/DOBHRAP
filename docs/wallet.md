# User account balances and manual store credit

Deploy on the existing hosting server:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
sudo ansible-playbook -i 'dobhrap,' -c local ansible/wallet-marketplace-oob.yml
```

This imports the existing staged release, live-backend backup, migrations, Tax Analyst and return workspace deployment. It adds a wallet schema check and verifies the wallet JavaScript. It does not credit any real user or make a purchase.

## Super Admin

Open **Super admin → Credit user accounts & balances** or **Platform → User balances & manual credits**. Choose the exact existing user (email and workspace are shown), choose currency, enter a positive amount in major currency units (10.00 USD means $10), and enter a reason. Credit appears immediately in that user's account balance. All balances and the latest ledger entries are visible in this management page.

Only a super administrator may grant credit. Server-side CSRF validation applies. Every entry records administrator, beneficiary, currency, amount, reason and request identifier. Repeating the same request identifier does not issue another credit; reusing it with different fields is rejected. The GUI preserves the identifier across an uncertain response so an accidental retry cannot duplicate the credit. There is no generic endpoint to overwrite a balance or erase ledger entries.

## User balance and purchases

The signed-in header shows **Balance**, with a separate amount for each funded currency. **Marketplace → Account balance** shows balance activity. The marketplace displays the available balance beside each offer and provides **Pay … from balance**.

Any eligible published one-time service or prepaid plan can be paid in full from a sufficient same-currency balance. User/tenant product restrictions still apply, including tax-only accounts. Wallet checkout does not need a card-payment gateway or a live provider API key, but the existing marketplace checkout switch and store-open control still apply. Read-only users cannot purchase. There is no automatic currency conversion or split payment.

Price is loaded from the server; client-supplied amounts are ignored. A conditional balance deduction, order, negative ledger entry, activated service and any purchased plan term are committed together. An insufficient balance or any failure rolls the entire purchase back. Repeating a purchase identifier returns the same order, and simultaneous purchases cannot overdraw the account.

Wallet orders use gateway/environment `wallet`, not a fabricated external live transaction. Tax Analyst sessions and tax-year preparation access accept a wallet order only when its debit ledger entry matches the order, user, currency and original amount. Test-mode card transactions still do not grant paid access. Wallet purchases appear in Marketplace orders, services and the account ledger. Fulfillment status changes preserve wallet service eligibility; subscription expiration/suspension rules remain in effect.

Manual credit is internal store credit. This release does not withdraw cash, initiate external refunds, automatically charge a payment method or issue accounting journal entries for wallet funding. Existing credits and purchases are never reset by deployment. Users' balances belong to their account, with currency separation, rather than being pooled across a workspace.
