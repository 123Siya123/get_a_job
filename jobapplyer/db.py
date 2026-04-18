from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from jobapplyer.models import ApplicationRecord, ApplicationStatus, JobOpportunity
from jobapplyer.utils import ensure_parent_dir, utcnow_iso


class Database:
    def __init__(self, path: Path):
        ensure_parent_dir(path)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._lock:
            cursor = self._conn.cursor()
            cursor.executescript(
                '''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL UNIQUE,
                    apply_url TEXT NOT NULL,
                    location TEXT,
                    sector TEXT,
                    discovered_at TEXT,
                    score REAL,
                    score_reason TEXT,
                    snippet TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS applications (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    apply_url TEXT NOT NULL,
                    outreach_channel TEXT NOT NULL,
                    last_event_at TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    application_id TEXT,
                    job_id TEXT,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );
                '''
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def has_application_for_url(self, source_url: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                'SELECT 1 FROM applications WHERE source_url = ? LIMIT 1',
                (source_url,),
            ).fetchone()
        return bool(row)

    def upsert_job(self, job: JobOpportunity) -> None:
        payload = (
            job.id,
            job.company,
            job.title,
            job.source_url,
            job.apply_url,
            job.location,
            job.sector,
            job.discovered_at,
            job.score,
            job.score_reason,
            job.snippet,
            json.dumps(job.metadata, ensure_ascii=True),
        )
        with self._lock:
            self._conn.execute(
                '''
                INSERT INTO jobs (
                    id, company, title, source_url, apply_url, location, sector,
                    discovered_at, score, score_reason, snippet, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    company=excluded.company,
                    title=excluded.title,
                    apply_url=excluded.apply_url,
                    location=excluded.location,
                    sector=excluded.sector,
                    score=excluded.score,
                    score_reason=excluded.score_reason,
                    snippet=excluded.snippet,
                    metadata_json=excluded.metadata_json
                ''',
                payload,
            )
            self._conn.commit()

    def upsert_application(self, application: ApplicationRecord) -> None:
        payload = (
            application.id,
            application.job_id,
            application.company,
            application.title,
            application.status.value,
            application.source_url,
            application.apply_url,
            application.outreach_channel,
            application.last_event_at,
            application.notes,
            json.dumps(application.metadata, ensure_ascii=True),
        )
        with self._lock:
            self._conn.execute(
                '''
                INSERT INTO applications (
                    id, job_id, company, title, status, source_url, apply_url,
                    outreach_channel, last_event_at, notes, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    last_event_at=excluded.last_event_at,
                    notes=excluded.notes,
                    metadata_json=excluded.metadata_json,
                    outreach_channel=excluded.outreach_channel,
                    apply_url=excluded.apply_url
                ''',
                payload,
            )
            self._conn.commit()

    def update_application_status(
        self,
        application_id: str,
        status: ApplicationStatus,
        notes: str = '',
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata_json = json.dumps(metadata or {}, ensure_ascii=True)
        with self._lock:
            self._conn.execute(
                '''
                UPDATE applications
                SET status = ?, notes = ?, last_event_at = ?, metadata_json = ?
                WHERE id = ?
                ''',
                (status.value, notes, utcnow_iso(), metadata_json, application_id),
            )
            self._conn.commit()

    def record_event(
        self,
        event_id: str,
        event_type: str,
        message: str,
        application_id: str = '',
        job_id: str = '',
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = (
            event_id,
            application_id or None,
            job_id or None,
            event_type,
            message,
            utcnow_iso(),
            json.dumps(metadata or {}, ensure_ascii=True),
        )
        with self._lock:
            self._conn.execute(
                '''
                INSERT OR REPLACE INTO events (
                    id, application_id, job_id, event_type, message, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                payload,
            )
            self._conn.commit()

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT * FROM jobs ORDER BY score DESC, discovered_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def list_applications(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT * FROM applications ORDER BY last_event_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def recent_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                'SELECT * FROM events ORDER BY created_at DESC LIMIT ?',
                (limit,),
            ).fetchall()
        return [self._row_to_payload(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            jobs = self._conn.execute('SELECT COUNT(*) AS c FROM jobs').fetchone()['c']
            apps = self._conn.execute('SELECT COUNT(*) AS c FROM applications').fetchone()['c']
            events = self._conn.execute('SELECT COUNT(*) AS c FROM events').fetchone()['c']
            statuses = self._conn.execute(
                'SELECT status, COUNT(*) AS c FROM applications GROUP BY status ORDER BY c DESC'
            ).fetchall()
        return {
            'jobs': jobs,
            'applications': apps,
            'events': events,
            'status_counts': {row['status']: row['c'] for row in statuses},
        }

    @staticmethod
    def _row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
        payload = dict(row)
        metadata_json = payload.pop('metadata_json', '{}')
        try:
            payload['metadata'] = json.loads(metadata_json or '{}')
        except json.JSONDecodeError:
            payload['metadata'] = {}
        return payload
