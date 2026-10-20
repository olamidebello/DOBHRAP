import fcntl
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import tax_automation_worker as worker


class TaxWorkerLockTests(unittest.TestCase):
    def test_lock_uses_runtime_directory_not_database_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            db=MagicMock();db.__enter__.return_value=db;db.execute.return_value=[]
            with patch.dict(os.environ,{'RUNTIME_DIRECTORY':directory}),patch.object(worker.app,'DB','/root/inaccessible/stale.db'),patch.object(worker.app,'connect',return_value=db):
                self.assertEqual(worker.run(),0)
            self.assertTrue((Path(directory)/'worker.lock').is_file())
    def test_second_worker_does_not_process_or_open_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with (Path(directory)/'worker.lock').open('a') as held:
                fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.dict(os.environ,{'RUNTIME_DIRECTORY':directory}),patch.object(worker.app,'connect') as connect:
                    self.assertEqual(worker.run(),0)
                connect.assert_not_called()
