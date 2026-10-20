# Use the hosting server for outgoing recovery email

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
sudo ansible-playbook -i 'dobhrap,' -c local ansible/local-mail-oob.yml
```

This installs the password UI/API and local Postfix with a dedicated OpenDKIM
signer. The application uses `127.0.0.1:25`, security mode `local`, no SMTP login,
and sender `noreply@olamideolatayobello.com`. External relays still require TLS.
The app refuses local mode on any other address/port or with saved credentials.
Switching to local mode clears saved Gmail/relay credentials. Postfix binds only
to loopback, accepts submissions only from the local host and sends directly to
recipient MX servers. Other local processes can submit mail too; this is a
trusted-host submission service. It does not install incoming mailboxes/webmail.

An unmanaged existing mail installation or conflicting port stops the installer
before replacing mail configuration. Existing DKIM private keys are preserved.
The dedicated signer must be available before Postfix starts; signing failures
temporarily defer mail. Postfix queues mail and retries delivery independently of
the web application. App acceptance means queued, not delivered to the inbox.

Defaults are hostname `mail.olamideolatayobello.com`, domain
`olamideolatayobello.com`, server IP `181.214.149.146` and selector `oob`.
Override `local_mail_hostname`, `local_mail_domain`, `local_mail_sender`,
`local_mail_public_ip` and `local_mail_selector` for another owned identity.
Changing the domain/selector requires publishing the corresponding DNS public key.

After installation:

```bash
sudo cat /var/log/oob-local-mail-dns.txt
sudo cat /var/log/oob-local-mail-readiness.json
sudo postqueue -p
sudo journalctl -u postfix -u oob-opendkim --since '15 minutes ago'
```

Publish the generated A and DKIM TXT records. Merge the server IP into the
existing SPF record; do not add a second SPF or discard other authorized senders.
Preserve an existing DMARC policy. The IP/hosting provider must configure PTR
reverse DNS to the mail hostname and permit outbound TCP port 25. The workflow
checks these requirements and writes a report; it does not claim to change DNS
or provider restrictions. It sends no test email. Re-run the readiness script or
playbook after DNS changes; then use Forgot password and verify receipt privately.

The application password-reset URL still expires after 15 minutes. Queued delivery
delays may make a received link expire; resolve mail delivery issues and request
a new link. If port 25 is blocked, direct delivery requires the provider to unblock
it or a permitted relay. DNS/network checks and local acceptance do not guarantee
inbox placement or reputation. No mailbox at Gmail is impersonated as the sender.

Primary references: https://www.postfix.org/BASIC_CONFIGURATION_README.html,
https://www.postfix.org/postconf.5.html and
https://manpages.debian.org/bookworm/opendkim/opendkim.conf.5.en.html.
