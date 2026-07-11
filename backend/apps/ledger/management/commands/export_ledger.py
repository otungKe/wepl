"""Immutable audit export of journals + lines.

Writes the full general-ledger trail (one row per journal line) as CSV — suitable
for handing to an auditor or archiving to WORM storage. Source is the immutable
JournalLine table, so the export is reproducible and tamper-evident.

    python manage.py export_ledger                 # CSV to stdout
    python manage.py export_ledger --output gl.csv # CSV to a file
    python manage.py export_ledger --start 2026-01-01 --end 2026-12-31
"""
import csv
import sys

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from apps.ledger.reporting import EXPORT_COLUMNS, export_journal_rows


class Command(BaseCommand):
    help = 'Export the general ledger (journals + lines) as CSV for audit.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='File path (default: stdout).')
        parser.add_argument('--start', help='ISO datetime lower bound (inclusive).')
        parser.add_argument('--end', help='ISO datetime upper bound (inclusive).')

    def handle(self, *args, **options):
        start = parse_datetime(options['start']) if options.get('start') else None
        end = parse_datetime(options['end']) if options.get('end') else None

        out = open(options['output'], 'w', newline='') if options.get('output') else sys.stdout
        try:
            writer = csv.DictWriter(out, fieldnames=list(EXPORT_COLUMNS))
            writer.writeheader()
            n = 0
            for row in export_journal_rows(start=start, end=end):
                writer.writerow(row)
                n += 1
        finally:
            if options.get('output'):
                out.close()
        if options.get('output'):
            self.stdout.write(self.style.SUCCESS(f"Exported {n} ledger line(s) → {options['output']}"))
