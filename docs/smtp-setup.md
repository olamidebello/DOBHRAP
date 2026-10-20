# Configure password recovery SMTP

From the existing server checkout:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
sudo ansible-playbook -i 'dobhrap,' -c local ansible/smtp-oob.yml
```

The playbook installs the password GUI/API, backs up the active SQLite or MySQL
database and verifies recovery tables. It then prompts privately for an SMTP
provider password. A blank input reuses a saved password. Existing SMTP values
are reused; an unconfigured installation defaults to smtp.gmail.com, STARTTLS
port 587, with dobcalldemo@gmail.com as username and sender. Supply the credential
issued for SMTP access by the provider; this script cannot create mail accounts,
enable provider-side access or issue provider passwords. Never paste credentials
into chat or pass passwords on the command line.

To use another authenticated relay, supply non-secret settings:

```bash
sudo ansible-playbook -i 'dobhrap,' -c local ansible/smtp-oob.yml \
  -e smtp_host=smtp.example.com -e smtp_port=587 \
  -e smtp_username=notifications@example.com \
  -e smtp_from=notifications@example.com -e smtp_security=starttls
```

Use `smtp_security=tls` and the provider's implicit TLS port when appropriate.
For unattended runs, place variables including `smtp_password` in an external
Ansible Vault file and pass `--ask-vault-pass -e @/private/smtp-vault.yml`.
Do not commit that file. Set `reset_service=dobhrap.service` only if that is the
actual installed web service; the default is oob-business.service.

The configuration helper reads the running service's database and encryption
settings. It verifies TLS certificates and hostname, authenticates when configured,
and checks SMTP NOOP before replacing settings. Values are encrypted in the
existing provider-settings table. Temporary input is root-owned, mode 0600 and
removed in Ansible's always block; task results suppress credentials. No web
service restart is needed after saving. The host must permit outbound access to
the relay. No local inbound mail server, mailbox, DNS record or open relay is created.

In the GUI, open **Super admin → Provider provisioning & keys → Password recovery
email**, then use **Connection checks → Test smtp** with the administrator password.
This verifies connection/authentication and sends no message. To verify delivery,
use **Forgot password** for your account and check its inbox and spam folder.
SMTP acceptance does not guarantee inbox delivery. Domain authentication and sender
authorization remain the mail provider/domain operator's responsibility.
