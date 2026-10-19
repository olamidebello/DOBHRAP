# MySQL migration for olamideolatayobello.com

Run on the hosting server, as root, from the DOBHRAP Git checkout:

```bash
cd /opt/dobhrap-watchdog-source
git pull --ff-only
ansible-playbook -i 'dobhrap,' -c local ansible/migrate-mysql-oob.yml
```

The playbook installs a dedicated Oracle MySQL 8.4 container, bound only to
127.0.0.1:3307 with a durable Docker volume and automatic restart. Existing
MySQL instances and other hosted sites are not reconfigured. Docker is installed
if absent. The image download and tests happen before the offline migration.

A fresh runtime is staged in /opt/dobhrap/releases. The real MySQL integration
tests run with random, isolated test schemas before production is paused.
The app, management broker and business workers then stop. Each registered
workspace is snapshotted, checked for SQLite integrity and foreign-key errors,
and copied to a separate MySQL schema. Every table's contents are SHA-256
verified in SQLite row order. Password hashes, IDs, encrypted payloads and
workspace boundaries are preserved. Encryption keys stay in the existing env.
Keys use VARCHAR(255); a source value exceeding that limit causes migration to
fail under strict SQL mode instead of silently truncating data.

The new runtime starts only after the copies verify. A database-backed HTTPS
check must confirm setup is still complete. Failure restores the prior release
and backend settings; candidate data and original SQLite files remain intact.
The old app was already failing database access, so restoring it does not
promise that the previous outage is resolved. Recurring timers resume after
success or rollback.

Read the result:

```bash
cat /var/lib/dobhrap/mysql-migration.json
cat /var/lib/oob-watchdog/status.json
cat /var/lib/oob-watchdog/gateway.json
systemctl status oob-business --no-pager
docker ps --filter name=dobhrap-mysql
```

The report points to the private source snapshots and per-table verification
report. The original SQLite databases are never deleted. Private credentials
are in /etc/dobhrap-mysql.json (root and the app group only). The backend switch
is /etc/dobhrap-mysql.env. Do not print either credential file in support logs.

Once MySQL has accepted new writes, rollback requires reconciling or restoring
those writes. Do not switch back to old SQLite files after normal use resumes.
The automatic rollback occurs before workers restart and before successful
cutover is declared. An activated backend stops a second migration attempt. A provisioning-only
failure can resume using the existing verified container and unused credentials.
Candidates containing imported tables require inspection before retrying.

The scheduled backup now creates private, compressed MySQL SQL dumps from one
consistent InnoDB snapshot across workspace schemas. They are retained for 14
days alongside the existing SQLite snapshots. Restore into an empty isolated
MySQL server first; the dump includes schema names, DDL and explicit columns.
Back up /etc/dobhrap.env, /etc/dobhrap-mysql.json and the encryption key separately
using your private backup process. Data cannot be decrypted without its key.

Development verification:

```bash
python -m unittest discover -s tests -p 'test_*.py'
OOB_TEST_MYSQL_CONFIG=/private/isolated-test-mysql.json \
  python -m unittest discover -s tests -p test_mysql.py
```

Tests use random dobhrap_test_* schemas and drop only those schemas. The test
configuration must point to an isolated MySQL server or the dedicated container;
never use credentials for unrelated services. Runtime SQL compatibility is
centralized in database.py. SQLite remains the default unless the backend env
explicitly selects MySQL; standalone SQLite repair playbooks must not be used
to roll back a live MySQL deployment.
