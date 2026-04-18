from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError

from jobapplyer.db import Database


class ApplicationLedger:
    def __init__(
        self,
        db: Database,
        export_dir: Path,
        google_sheet_id: str = '',
        worksheet_name: str = 'Applications',
        service_account_file: str = '',
    ):
        self.db = db
        self.export_dir = export_dir
        self.google_sheet_id = google_sheet_id
        self.worksheet_name = worksheet_name
        self.service_account_file = service_account_file
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_csv(self) -> Path:
        path = self.export_dir / 'applications.csv'
        rows = self.db.list_applications(limit=500)
        headers = [
            'company',
            'title',
            'status',
            'outreach_channel',
            'source_url',
            'apply_url',
            'last_event_at',
            'notes',
        ]
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, '') for key in headers})
        return path

    def sync_google_sheet(self) -> dict[str, Any]:
        if not (self.google_sheet_id and self.service_account_file):
            return {'enabled': False, 'updated': False}
        try:
            import gspread

            client = gspread.service_account(filename=self.service_account_file)
            spreadsheet = client.open_by_key(self.google_sheet_id)
            try:
                worksheet = spreadsheet.worksheet(self.worksheet_name)
            except gspread.WorksheetNotFound:
                worksheet = spreadsheet.add_worksheet(title=self.worksheet_name, rows=200, cols=12)
            rows = self.db.list_applications(limit=500)
            table = [[
                'Company',
                'Title',
                'Status',
                'Channel',
                'Source URL',
                'Apply URL',
                'Last Event',
                'Notes',
            ]]
            for row in rows:
                table.append([
                    row.get('company', ''),
                    row.get('title', ''),
                    row.get('status', ''),
                    row.get('outreach_channel', ''),
                    row.get('source_url', ''),
                    row.get('apply_url', ''),
                    row.get('last_event_at', ''),
                    row.get('notes', ''),
                ])
            worksheet.clear()
            worksheet.update('A1', table)
            return {'enabled': True, 'updated': True, 'rows': max(len(table) - 1, 0)}
        except (GoogleAuthError, OSError, Exception) as exc:
            return {'enabled': True, 'updated': False, 'error': str(exc)}
