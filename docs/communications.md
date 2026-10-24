# Managed phone, PBX and system email

Registration commits two durable provisioning records. When the persistent encryption key is configured, each receives a distinct encrypted random service password; otherwise records remain empty until commissioning, without blocking signup or storing plaintext credentials. The existing platform password is never copied to SIP or email. The minute timer backfills existing users and invited employees. Personal accounts receive SIP phone access. Business, court and other organizational accounts receive a tenant-isolated PBX workspace; each organization user receives a SIP account and extension, and its administrator receives tenant administrator access. Choose the Business, court or organization registration option for any non-individual account.

The **Phone, PBX & system email** navigation destination works for personal and business accounts. It provides provisioning status, retries, a link to the actual SIP portal, password-confirmed access to the user's own managed credentials, inbox previews, a compose form, outgoing-message status and super administrator provisioning controls. The phone portal opens separately and requires its managed login: this is not single sign-on or an embedded dialer. Existing SIP accounts with matching email addresses require operator-assisted linkage; this bridge does not take them over. Password changes made directly in a service require operator reconciliation with the encrypted managed record.

## Deployment

Both repositories must be updated. These commands deploy to existing installations; do not run the SIP playbook on the application host.

1. On the **SIP server**, using its existing `/opt/olamide/repo` checkout:

```bash
cd /opt/olamide/repo
git pull --ff-only origin main
ansible-playbook deployment/ansible/hosted-accounts.yml
```

The SIP playbook locks against other deployments, backs up the database, preserves a root-only service token, builds/tests the API image, runs additive migrations and checks public health and unauthenticated endpoint rejection. It retains the previous API image for recovery. Its environment files must be root-owned and mode 0600. Existing switch provisioning and credential encryption configuration are preserved.

2. On **154.16.170.86**, privately copy the token from the SIP server. Replace `YOUR_SIP_SERVER` with its actual SSH address; never paste the token into chat:

```bash
scp root@YOUR_SIP_SERVER:/root/dobhrap-sip-bridge-token /root/dobhrap-sip-bridge-token
chmod 600 /root/dobhrap-sip-bridge-token
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
ansible-playbook -i 'dobhrap,' -c local ansible/communications-oob.yml
```

This deploys the complete application and commissions the timer. The private token is imported into encrypted Provider provisioning & keys. Re-running preserves the same installation identity and service passwords. Keep the application database and encryption key together in backups; changing the installation UUID creates a new external identity namespace.

3. For **mailboxes**, the existing local OlamidePanel installation must have its mail stack, TLS certificate, mailbox worker, and approved domain delegation configured. Commissioning reads `/etc/olamidepanel/mail-policy.json` and the domain delegation for `olamideolatayobello.com`. It enables email only when those prerequisites exist. It does not install or replace a mail server. The configured domain must be approved by the root mail policy and delegated to an active panel operator. Mailbox provisioning uses that operator and the existing panel mailbox worker. No arbitrary system commands are accepted from the GUI.

If these prerequisites are absent, the GUI remains available and mail provisioning stays disabled. Complete the panel's existing domain-email and mailbox-GUI deployment first, then rerun commissioning. DNS MX, SPF, DKIM, DMARC, TLS and reverse DNS must be verified for public delivery; a created mailbox is not proof that public delivery works.

## Operation and boundaries

- Mail addresses are stable generated identities: `u<installation-prefix>-<user-id>@olamideolatayobello.com`. Existing unowned mailboxes are never overwritten. Panel jobs with uncertain outcomes require operator review.
- Inbox previews use verified TLS on IMAP port 993, read-only access, at most 20 messages and bounded plain text previews. HTML and attachments are not rendered. Use a mail client for full messages and attachments.
- Sending uses authenticated SMTP port 587 with verified STARTTLS, a maximum of five recipients and 64 KB plain text per message, and 25 queued messages per user per day. Requests use durable idempotency keys. `sent` means SMTP acceptance, `partial` means some recipients were rejected, and `uncertain` requires review. Uncertain messages are never automatically resent.
- Existing password recovery and platform notification SMTP settings remain under Provider provisioning & keys; per-user mailboxes are separate from that system sender.
- SIP states reflect the existing switch provisioner. `awaiting_switch` is not an active phone. Paid calling, subscriptions, DIDs, trunks, forwarding and production PBX routing are not purchased or activated by signup. Use the existing SIP portal's controls and readiness checks for those services.
- Provisioning flags stop new work and queued sending; they do not delete existing service accounts. Suspension/deletion and password changes in the source platform do not automatically revoke independent SIP or mail credentials. Administrators must also manage those accounts in their respective services. This release provisions accounts; it is not a complete identity lifecycle synchronizer.
- Managed credentials are encrypted at rest and revealed only after confirming the current platform password. Super administrator job tables contain metadata, not other users' passwords. Root commissioning configuration is `/etc/dobhrap-communications.env`; logs must not contain tokens or mailbox credentials.

Inspect the timer with `systemctl status dobhrap-communications.timer`; inspect sanitized worker failures with `journalctl -u dobhrap-communications.service`. Failed jobs appear as `attention` in the GUI; correct the provider configuration and use Retry provisioning. Back up the database before changing identity mappings manually.
