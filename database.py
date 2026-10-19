"""Database boundary. SQLite remains available for rollback and offline tools.

MySQL 8.0.16+ uses InnoDB, binary utf8mb4 collation, strict SQL mode and
one schema per workspace. Only this module translates the existing SQL dialect.
"""
import functools
import json
import os
from pathlib import Path
import re
import sqlite3


def mysql_enabled():
    return os.environ.get('DOBHRAP_DB_BACKEND', 'sqlite') == 'mysql'


def config():
    path = Path(os.environ.get('DOBHRAP_MYSQL_CONFIG', '/etc/dobhrap-mysql.json'))
    return json.loads(path.read_text())


def schema_name(tenant_id=1):
    tenant_id = int(tenant_id)
    if tenant_id < 1:
        raise ValueError('Invalid workspace')
    prefix = config().get('prefix', 'dobhrap')
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,30}', prefix):
        raise ValueError('Invalid database prefix')
    return prefix + ('_platform' if tenant_id == 1 else '_tenant_' + str(tenant_id))


def connect(path=None, tenant_id=1, create=False):
    if mysql_enabled():
        return MySQLConnection(schema_name(tenant_id), create=create)
    c = sqlite3.connect(path or os.environ.get('DOBHRAP_DB', 'data/dobhrap.db'), timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return list(self.values())[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, rows=(), rowcount=0, lastrowid=None):
        self.rows = iter(rows)
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


@functools.lru_cache(maxsize=2048)
def parsed(sql):
    import sqlglot
    return sqlglot.parse_one(sql, read='sqlite')


def ddl(sql):
    """Translate declared schemas, keeping payloads unbounded and keys indexed."""
    from sqlglot import exp
    tree = parsed(sql).copy()
    schema = tree.this
    if not isinstance(schema, exp.Schema):
        raise ValueError('Unsupported MySQL schema statement')
    columns = list(schema.find_all(exp.ColumnDef))
    keyed = set()
    for key in schema.find_all(exp.PrimaryKey, exp.UniqueColumnConstraint):
        for ident in key.find_all(exp.Identifier):
            keyed.add(ident.name)
    for col in columns:
        if any(isinstance(c.kind, (exp.PrimaryKeyColumnConstraint, exp.UniqueColumnConstraint, exp.Reference)) for c in col.constraints):
            keyed.add(col.name)
    # These fields are indexed by the two attendance uniqueness invariants.
    keyed.update({'worker_id', 'ssn_hash'})
    fks = []
    integer_primary = None
    for col in columns:
        kind = col.args['kind'].this
        primary = any(isinstance(c.kind, exp.PrimaryKeyColumnConstraint) for c in col.constraints)
        timestamp = any(isinstance(c.kind, exp.DefaultColumnConstraint) and isinstance(c.kind.this, exp.CurrentTimestamp) for c in col.constraints)
        if kind in (exp.DataType.Type.INT, exp.DataType.Type.BIGINT):
            col.set('kind', exp.DataType.build('BIGINT'))
            if primary:
                integer_primary = col.name
                if not any(isinstance(c.kind, exp.CheckColumnConstraint) for c in col.constraints):
                    col.append('constraints', exp.ColumnConstraint(kind=exp.AutoIncrementColumnConstraint()))
        elif kind == exp.DataType.Type.TEXT:
            col.set('kind', exp.DataType.build('VARCHAR(255)' if col.name in keyed else 'DATETIME' if timestamp else 'LONGTEXT'))
            # MySQL requires expression defaults for TEXT values.
            for constraint in col.constraints:
                if isinstance(constraint.kind, exp.DefaultColumnConstraint) and col.name not in keyed and not timestamp:
                    constraint.kind.set('this', exp.Paren(this=constraint.kind.this))
        constraints = []
        for constraint in col.constraints:
            if isinstance(constraint.kind, exp.Reference):
                fks.append(exp.ForeignKey(expressions=[exp.to_identifier(col.name)], reference=constraint.kind.copy()))
            else:
                constraints.append(constraint)
        col.set('constraints', constraints)
    if not integer_primary:
        schema.append('expressions', exp.ColumnDef(this=exp.to_identifier('_oob_seq'), kind=exp.DataType.build('BIGINT'), constraints=[exp.ColumnConstraint(kind=exp.NotNullColumnConstraint()), exp.ColumnConstraint(kind=exp.UniqueColumnConstraint()), exp.ColumnConstraint(kind=exp.AutoIncrementColumnConstraint())]))
    schema.set('expressions', schema.expressions + fks)
    return tree.sql(dialect='mysql', identify=True) + ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'


class MySQLConnection:
    def __init__(self, schema, create=False):
        import pymysql
        options = config()
        self.schema = schema
        self._locked = False
        self.in_transaction = False
        self._columns = {}
        self._rowids = {}
        try:
            self.raw = pymysql.connect(host=options.get('host', '127.0.0.1'), port=int(options.get('port', 3307)), user=options['user'], password=options['password'], charset='utf8mb4', autocommit=True, connect_timeout=10, read_timeout=60, write_timeout=60, cursorclass=pymysql.cursors.DictCursor, conv={**pymysql.converters.conversions, 7: str, 10: str, 12: str})
        except pymysql.err.MySQLError as exc:
            raise sqlite3.OperationalError('MySQL connection unavailable') from exc
        try:
            with self.raw.cursor() as c:
                c.execute("SET SESSION sql_mode='STRICT_ALL_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'")
                c.execute("SET SESSION time_zone='+00:00'")
                if create:
                    c.execute('CREATE DATABASE IF NOT EXISTS `' + schema + '` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
                self.raw.select_db(schema)
        except Exception:
            self.raw.close()
            raise

    def _query(self, sql, params=None):
        import pymysql
        try:
            with self.raw.cursor() as c:
                c.execute(sql, params)
                rows = [Row({k: v for k, v in r.items() if not k.startswith('_oob_') and k != '_open_worker'}) for r in c.fetchall()] if c.description else []
                # SUM(BIGINT) is returned as Decimal; existing API expects JSON integers.
                from decimal import Decimal
                for row in rows:
                    for k, v in row.items():
                        if isinstance(v, Decimal):
                            row[k] = int(v) if v == v.to_integral_value() else float(v)
                return Result(rows, c.rowcount, c.lastrowid)
        except pymysql.err.IntegrityError as exc:
            raise sqlite3.IntegrityError('Database constraint violation') from exc
        except pymysql.err.MySQLError as exc:
            raise sqlite3.OperationalError('MySQL operation failed (code %s)' % exc.args[0]) from exc

    def columns(self, table):
        if table not in self._columns:
            rows = self._query('SELECT COLUMN_NAME,COLUMN_KEY,DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION', (self.schema, table)).fetchall()
            self._columns[table] = [r['COLUMN_NAME'] for r in rows if r['COLUMN_NAME'] not in ('_oob_seq', '_open_worker')]
            self._rowids[table] = '_oob_seq' if any(r['COLUMN_NAME'] == '_oob_seq' for r in rows) else next(r['COLUMN_NAME'] for r in rows if r['COLUMN_KEY']=='PRI' and r['DATA_TYPE']=='bigint')
        return self._columns[table]

    def begin(self):
        if self.in_transaction:
            return
        # Match SQLite's single writer behavior across web/worker processes. SELECTs
        # before BEGIN run in autocommit, so the lock precedes the first snapshot.
        result = self._query('SELECT GET_LOCK(%s,30) acquired', ('oob:' + self.schema,)).fetchone()
        if result['acquired'] != 1:
            raise sqlite3.OperationalError('Database writer is busy')
        self._locked = True
        self.raw.begin()
        self.in_transaction = True

    def _release(self):
        self.in_transaction = False
        if self._locked:
            self._locked = False
            self._query('SELECT RELEASE_LOCK(%s)', ('oob:' + self.schema,))

    def commit(self):
        try:
            self.raw.commit()
        finally:
            self._release()

    def rollback(self):
        try:
            self.raw.rollback()
        finally:
            self._release()

    def close(self):
        try:
            self.rollback()
        finally:
            self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.rollback() if kind else self.commit()
        finally:
            self.raw.close()

    def executescript(self, sql):
        import sqlglot
        self.commit()
        for tree in sqlglot.parse(sql, read='sqlite'):
            if tree:
                self.execute(tree.sql(dialect='sqlite'))

    def execute(self, sql, params=()):
        from sqlglot import exp
        sql = sql.strip().rstrip(';')
        if sql.upper() in ('BEGIN IMMEDIATE', 'BEGIN', 'BEGIN TRANSACTION'):
            self.begin()
            return Result()
        if sql.upper() == 'PRAGMA FOREIGN_KEYS=ON':
            return Result()
        if sql.upper() == 'PRAGMA QUICK_CHECK':
            self._query('SELECT 1')
            return Result([Row(quick_check='ok')])
        pragma = re.fullmatch(r'PRAGMA table_info\((\w+)\)', sql, re.I)
        if pragma:
            return Result([Row(cid=i, name=name) for i, name in enumerate(self.columns(pragma[1]))])
        if 'sqlite_master' in sql:
            # Used only by the fixed admin broker to check whether its queue exists.
            return self._query("SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='platform_jobs'", (self.schema,))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        month = now.year * 12 + now.month - 1 - 5
        first_month = '%04d-%02d-01' % (month // 12, month % 12 + 1)
        sql = sql.replace("date('now','start of month','-5 months')", "'" + first_month + "'")
        tree = parsed(sql).copy()
        if isinstance(tree, exp.Create) and tree.args.get('kind') == 'TABLE':
            self.commit()
            self._query('SET FOREIGN_KEY_CHECKS=0')
            try:
                result = self._query(ddl(sql))
            finally:
                self._query('SET FOREIGN_KEY_CHECKS=1')
            self._columns.clear()
            return result
        if isinstance(tree, exp.Create) and tree.args.get('kind') == 'INDEX':
            # Preserve SQLite partial uniqueness using generated nullable keys.
            name = tree.this.name
            existing = self._query('SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s', (self.schema, tree.this.args['table'].name, name)).fetchone()
            if existing:
                return Result()
            self.commit()
            if name == 'clock_one_open':
                return self._query('ALTER TABLE clock_entries ADD COLUMN _open_worker VARCHAR(255) GENERATED ALWAYS AS (CASE WHEN ended IS NULL THEN worker_id ELSE NULL END) STORED, ADD UNIQUE INDEX clock_one_open (_open_worker)')
            if name == 'clock_ssn_unique':
                return self._query('CREATE UNIQUE INDEX clock_ssn_unique ON clock_workers(ssn_hash)')
            raise ValueError('Unsupported MySQL index')
        if isinstance(tree, exp.Alter):
            self.commit()
            for col in tree.find_all(exp.ColumnDef):
                col.set('kind', exp.DataType.build('VARCHAR(255)' if col.name == 'ssn_hash' else 'BIGINT' if col.args['kind'].this == exp.DataType.Type.INT else 'LONGTEXT'))
            for constraint in col.constraints:
                    if isinstance(constraint.kind, exp.DefaultColumnConstraint) and col.args['kind'].this == exp.DataType.Type.LONGTEXT:
                        constraint.kind.set('this', exp.Paren(this=constraint.kind.this))
            self._columns.clear()
        if isinstance(tree, (exp.Insert, exp.Update, exp.Delete)):
            self.begin()
        if isinstance(tree, exp.Insert):
            table = tree.this.this if isinstance(tree.this, exp.Schema) else tree.this
            if not isinstance(tree.this, exp.Schema):
                tree.set('this', exp.Schema(this=table, expressions=[exp.to_identifier(n) for n in self.columns(table.name) if not n.startswith('_')]))
            conflict = tree.args.get('conflict')
            alternative = tree.args.get('alternative')
            if conflict:
                conflict.set('duplicate', True)
                conflict.set('conflict_keys', None)
                conflict.set('action', exp.Var(this='UPDATE'))
                for column in conflict.find_all(exp.Column):
                    if column.table == 'excluded':
                        column.replace(exp.Anonymous(this='VALUES', expressions=[exp.column(column.name)]))
            elif alternative == 'IGNORE':
                name = self.columns(table.name)[0]
                tree.set('conflict', exp.OnConflict(duplicate=True, expressions=[exp.EQ(this=exp.column(name), expression=exp.column(name))], action=exp.Var(this='UPDATE')))
                tree.set('alternative', None)
            elif alternative == 'REPLACE':
                tree.set('alternative', None)
                # SQLite REPLACE is used for settings rows; UPDATE preserves references.
                names = self.columns(table.name)
                tree.set('conflict', exp.OnConflict(duplicate=True, expressions=[exp.EQ(this=exp.column(n), expression=exp.Anonymous(this='VALUES', expressions=[exp.column(n)])) for n in names], action=exp.Var(this='UPDATE')))
        tables = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
        for column in list(tree.find_all(exp.Column)):
            if column.name.lower() == 'rowid':
                table = tables.get(column.table) if column.table else next(iter(tables.values()), None)
                if not table:
                    raise ValueError('Ambiguous row order')
                self.columns(table)
                column.set('this', exp.to_identifier(self._rowids[table]))
        for node in list(tree.find_all(exp.JSONExtract)):
            node.replace(exp.JSONExtractScalar(this=node.this, expression=node.expression))
        update_where = tree.args.get('where').copy() if isinstance(tree, exp.Update) and tree.args.get('where') else None
        update_table = tree.this.copy() if isinstance(tree, exp.Update) else None
        where_count = len(list(update_where.find_all(exp.Placeholder))) if update_where else 0
        # Replace AST placeholders, never interpolate or alter question marks in data.
        for node in list(tree.find_all(exp.Placeholder)):
            node.replace(exp.Var(this='__OOB_PARAMETER__'))
        output = tree.sql(dialect='mysql', identify=True)
        output = output.replace('%', '%%').replace('__OOB_PARAMETER__', '%s')
        result = self._query(output, tuple(params))
        if isinstance(tree, exp.Update) and result.rowcount == 0:
            count = exp.select(exp.Count(this=exp.Star()).as_('matched')).from_(update_table)
            if update_where:
                count.set('where', update_where)
            for node in list(count.find_all(exp.Placeholder)):
                node.replace(exp.Var(this='__OOB_PARAMETER__'))
            query = count.sql(dialect='mysql', identify=True).replace('%', '%%').replace('__OOB_PARAMETER__', '%s')
            result.rowcount = self._query(query, tuple(params[-where_count:]) if where_count else ()).fetchone()['matched']
        return result
