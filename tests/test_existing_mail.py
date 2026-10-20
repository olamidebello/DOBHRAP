import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

spec=importlib.util.spec_from_file_location('existing_mail',Path(__file__).resolve().parents[1]/'ansible/existing-mail-probe.py')
mail=importlib.util.module_from_spec(spec);spec.loader.exec_module(mail)


class ExistingMailTests(unittest.TestCase):
    def client(self):
        smtp=MagicMock();smtp.__enter__.return_value=smtp
        smtp.mail.return_value=(250,b'OK');smtp.rcpt.return_value=(250,b'OK')
        return smtp
    def test_acceptance_probe_never_sends_message(self):
        smtp=self.client()
        with patch.object(mail.smtplib,'SMTP',return_value=smtp):
            result=mail.probe('noreply@example.com','owner@example.net')
        self.assertTrue(result['local_submission_accepted'])
        self.assertFalse(result['message_sent'])
        smtp.data.assert_not_called();smtp.sendmail.assert_not_called();smtp.send_message.assert_not_called()
        smtp.rset.assert_called_once()
    def test_relay_denied_stops_without_sending(self):
        smtp=self.client();smtp.rcpt.return_value=(554,b'Relay denied')
        with patch.object(mail.smtplib,'SMTP',return_value=smtp):
            with self.assertRaises(RuntimeError):mail.probe('noreply@example.com','owner@example.net')
        smtp.rset.assert_called_once();smtp.data.assert_not_called()
    def test_header_injection_rejected_before_connection(self):
        with patch.object(mail.smtplib,'SMTP') as smtp:
            with self.assertRaises(ValueError):mail.probe('a@example.com\nBcc:b@example.com','c@example.com')
        smtp.assert_not_called()
