import gzip
import os
import shutil
import subprocess
from datetime import datetime

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = ('Back up the database to BACKUP_DIR (gzip). Uses pg_dump for PostgreSQL when it is installed, '
            'otherwise a Django JSON dump (restore with loaddata). Keeps the newest BACKUP_KEEP files.')

    def handle(self, *args, **options):
        folder = settings.BACKUP_DIR
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        db = settings.DATABASES['default']
        target = None
        if connection.vendor == 'postgresql' and shutil.which('pg_dump'):
            cmd = ['pg_dump', '--no-owner', '--no-privileges', '-h', db.get('HOST') or 'localhost',
                   '-p', str(db.get('PORT') or 5432), '-U', db.get('USER') or '', db['NAME']]
            result = subprocess.run(cmd, capture_output=True, env={**os.environ, 'PGPASSWORD': db.get('PASSWORD') or ''})
            if result.returncode == 0:
                target = folder / f'smartcart-{stamp}.sql.gz'
                with gzip.open(target, 'wb') as fh:
                    fh.write(result.stdout)
            else:
                # Usually an older pg_dump than the server. The JSON dump below works with any version.
                self.stderr.write(f'pg_dump failed, saving a JSON dump instead: {result.stderr.decode()[:200].strip()}')
        if target is None:
            target = folder / f'smartcart-{stamp}.json.gz'
            with gzip.open(target, 'wt', encoding='utf-8') as fh:
                call_command('dumpdata', '--natural-foreign', '--natural-primary', '--exclude=contenttypes',
                             '--exclude=auth.permission', '--exclude=sessions', '--exclude=axes', stdout=fh)
        backups = sorted(folder.glob('smartcart-*.gz'), reverse=True)
        for old in backups[settings.BACKUP_KEEP:]:
            old.unlink()
        size = target.stat().st_size / 1024
        self.stdout.write(self.style.SUCCESS(f'Backup saved: {target} ({size:,.0f} KB). '
                                             f'Keeping the newest {settings.BACKUP_KEEP}.'))
