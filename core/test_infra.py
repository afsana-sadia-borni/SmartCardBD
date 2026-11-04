import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .sms import SMSError, send_sms

SMS_ON = {'SMS_API_KEY': 'key', 'SMS_SENDER_ID': '8809617000000'}


class SMSTests(TestCase):
    def test_logged_only_without_a_provider(self):
        with mock.patch('core.sms.requests.post') as post:
            self.assertEqual(send_sms('01712345678', 'hi'), 'console')
        post.assert_not_called()

    @override_settings(**SMS_ON)
    @mock.patch('core.sms.requests.post')
    def test_sends_through_bulksmsbd(self, post):
        post.return_value.json.return_value = {'response_code': 202}
        self.assertEqual(send_sms('+8801712-345678', 'Hello'), 'sent')
        data = post.call_args.kwargs['data']
        self.assertEqual((data['number'], data['senderid'], data['message']), ('8801712345678', '8809617000000', 'Hello'))

    @override_settings(**SMS_ON)
    @mock.patch('core.sms.requests.post')
    def test_provider_errors_and_bad_numbers(self, post):
        post.return_value.json.return_value = {'response_code': 1007, 'error_message': 'Balance Insufficient'}
        with self.assertRaisesMessage(SMSError, '1007'):
            send_sms('01712345678', 'x')
        with self.assertRaises(SMSError):
            send_sms('12345', 'x')


class OpsTests(TestCase):
    def test_healthz(self):
        response = self.client.get(reverse('healthz'))
        self.assertEqual(response.json(), {'status': 'ok', 'database': 'ok', 'cache': 'ok'})

    def test_backup_keeps_the_newest_files(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(BACKUP_DIR=Path(folder), BACKUP_KEEP=2):
            with mock.patch('core.management.commands.backup_db.shutil.which', return_value=None):
                for stamp in ('20260101-000000', '20260102-000000', '20260103-000000'):
                    with mock.patch('core.management.commands.backup_db.datetime') as dt:
                        dt.now.return_value.strftime.return_value = stamp
                        call_command('backup_db', stdout=StringIO())
            files = sorted(p.name for p in Path(folder).iterdir())
        self.assertEqual(files, ['smartcart-20260102-000000.json.gz', 'smartcart-20260103-000000.json.gz'])

    def test_test_email_and_sms_commands(self):
        out = StringIO()
        call_command('send_test_email', 'me@example.com', stdout=out)
        self.assertEqual(mail.outbox[0].to, ['me@example.com'])
        call_command('send_test_sms', '01712345678', stdout=out)
        self.assertIn('Logged only', out.getvalue())
