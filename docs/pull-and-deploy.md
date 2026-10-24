# Pull and deploy on the existing application server

Run as root on **154.16.170.86**, where `/etc/dobhrap.env` and the existing application database are already installed:

```bash
apt-get update
apt-get install -y ansible git
ansible-pull -U https://github.com/olamidebello/DOBHRAP.git -C main \
  -d /opt/dobhrap-pull-bootstrap -i localhost, -c local \
  ansible/pull-and-deploy.yml
```

The separate bootstrap checkout retrieves the deployment instructions. The playbook installs prerequisites, locks concurrent pulls, creates or fast-forwards `/opt/dobhrap-watchdog-source`, then runs `communications-oob.yml`. That existing deployment builds an isolated release, runs the application tests, preserves runtime configuration, applies schema migrations, updates the services, checks public HTTPS and commissions the communications timer. It does not transfer data from another server or create a replacement administrator.

Existing tracked edits, untracked files, a different remote, a different branch or a non-forward history stop deployment. No forced reset or cleanup occurs. Ignored runtime files remain untouched. Keep the source checkout root-owned and protected from writes by application users. Detailed deployment output is saved in a root-only file under `/var/log/dobhrap-deploy/`; the command reports its exact path if deployment fails. Existing release/database backups remain managed by the full deployment playbook. A failed deployment must be reviewed using its log; this wrapper does not promise database rollback.

For an existing clean checkout, the equivalent shorter invocation is:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only origin main
ansible-playbook -i localhost, -c local ansible/pull-and-deploy.yml
```

This is the **application-host** deployment. Before phone provisioning can activate, install the SIP repository's `deployment/ansible/hosted-accounts.yml` on the SIP host and privately copy its `/root/dobhrap-sip-bridge-token` to this application host. Email requires the approved local OlamidePanel mail stack, delegated domain and mailbox worker. The wrapper does not obtain SSH passwords, print tokens, purchase calling plans, or claim that unconfigured external services are working. See [communications.md](communications.md) for the complete two-server commissioning procedure.

The staged release and virtual environment are root-owned with runtime-group read/traversal access. A runtime-account Python preflight now runs before the maintenance window. If data access, snapshot or activation fails in that window, the playbook attempts to restart previously running application services and active timers, then reports failure. It does not reset data or promise recovery after every later configuration failure.

The pull playbook also verifies that registration OTP, global user management and activity-log JavaScript are served over public HTTPS. Startup creates the required OTP, user-profile, deletion-queue and activity tables. Twilio remains disabled until a super administrator saves credentials, provisions/tests the Verify service and enables the registration policy. Existing Twilio settings are preserved; this deployment does not send a verification SMS.
