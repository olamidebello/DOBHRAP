import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import advanced

class WatchdogReports(unittest.TestCase):
 def test_role_boundary_applies_even_without_database(self):
  for role in ('viewer','editor','admin'):
   with self.assertRaises(advanced.ServiceError) as result:app.watchdog_report(role)
   self.assertEqual(result.exception.status,403)
 def test_missing_report_is_explicit(self):
  with patch.object(app,'WATCHDOG_DB','/nonexistent-watchdog/events.db'):
   self.assertFalse(app.watchdog_report('super_admin')['installed'])
 def test_history_order_summary_and_staleness(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'events.db'
   with sqlite3.connect(path) as c:
    c.execute('CREATE TABLE watchdog_events(id INTEGER PRIMARY KEY,checked_at INTEGER,action TEXT,failures INTEGER,service TEXT,checks TEXT)')
    for age,action in ((100000,'restart_failed'),(60,'recovered')):
     c.execute('INSERT INTO watchdog_events VALUES(NULL,?,?,?,?,?)',(int(time.time())-age,action,0,'oob-business.service',json.dumps({'database':True})))
   with patch.object(app,'WATCHDOG_DB',str(path)):
    result=app.watchdog_report('super_admin')
   self.assertEqual(result['latest']['action'],'recovered')
   self.assertEqual(result['summary'],{'recovered':1})
   self.assertFalse(result['stale'])
   self.assertEqual(len(result['events']),2)
 def test_invalid_schema_returns_safe_service_error(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'events.db';sqlite3.connect(path).close()
   with patch.object(app,'WATCHDOG_DB',str(path)):
    with self.assertRaises(advanced.ServiceError) as result:app.watchdog_report('super_admin')
   self.assertEqual(result.exception.status,503)
