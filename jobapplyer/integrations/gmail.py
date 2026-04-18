from __future__ import annotations

import asyncio
import email
import imaplib
from email.header import decode_header
from typing import Any

from jobapplyer.db import Database
from jobapplyer.models import ApplicationStatus
from jobapplyer.utils import slugify


class GmailWatcher:
    def __init__(self, host: str, address: str, app_password: str, db: Database):
        self.host = host
        self.address = address
        self.app_password = app_password
        self.db = db

    async def sync(self) -> list[dict[str, Any]]:
        if not self.address or not self.app_password:
            return []
        return await asyncio.to_thread(self._sync_blocking)

    def _sync_blocking(self) -> list[dict[str, Any]]:
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.address, self.app_password)
        mail.select('INBOX')
        status, data = mail.search(None, 'ALL')
        if status != 'OK':
            return []
        message_ids = data[0].split()[-25:]
        results: list[dict[str, Any]] = []
        applications = self.db.list_applications(limit=500)

        for message_id in reversed(message_ids):
            status, payload = mail.fetch(message_id, '(BODY.PEEK[])')
            if status != 'OK' or not payload:
                continue
            raw_message = payload[0][1]
            parsed = email.message_from_bytes(raw_message)
            sender = self._decode_header(parsed.get('From', ''))
            subject = self._decode_header(parsed.get('Subject', ''))
            snippet = self._extract_snippet(parsed)
            matched = self._match_application(sender, subject, snippet, applications)
            if not matched:
                continue
            classification = self._classify(sender, subject, snippet)
            if classification:
                self.db.update_application_status(
                    matched['id'],
                    classification,
                    notes=f'Email update from {sender}: {subject}',
                    metadata={'sender': sender, 'subject': subject},
                )
                self.db.record_event(
                    event_id=slugify(f"mail-{matched['id']}-{subject[:48]}"),
                    event_type='gmail_status_update',
                    message=f'{classification.value}: {subject}',
                    application_id=matched['id'],
                    job_id=matched['job_id'],
                    metadata={'sender': sender},
                )
                results.append({'application_id': matched['id'], 'status': classification.value, 'subject': subject})
        mail.logout()
        return results

    def _match_application(self, sender: str, subject: str, snippet: str, applications: list[dict[str, Any]]) -> dict[str, Any] | None:
        haystack = f'{sender} {subject} {snippet}'.lower()
        for application in applications:
            company = (application.get('company') or '').lower()
            title = (application.get('title') or '').lower()
            if company and company in haystack:
                return application
            if title and any(word for word in title.split() if len(word) > 4 and word in haystack):
                return application
        return None

    def _classify(self, sender: str, subject: str, snippet: str) -> ApplicationStatus | None:
        text = f'{sender} {subject} {snippet}'.lower()
        if any(term in text for term in ['unfortunately', 'not moving forward', 'decline', 'rejection', 'absage']):
            return ApplicationStatus.declined
        if any(term in text for term in ['interview', 'availability', 'schedule', 'meeting', 'conversation']):
            return ApplicationStatus.interview
        if any(term in text for term in ['offer', 'congratulations', 'we would like to hire']):
            return ApplicationStatus.offer
        if any(term in text for term in ['assessment', 'test', 'complete this', 'questionnaire']):
            return ApplicationStatus.needs_action
        if any(term in text for term in ['received your application', 'thank you for applying', 'under review']):
            return ApplicationStatus.in_review
        return None

    @staticmethod
    def _extract_snippet(message: email.message.Message) -> str:
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == 'text/plain':
                    try:
                        return part.get_payload(decode=True).decode(errors='ignore')[:1200]
                    except Exception:
                        continue
        payload = message.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(errors='ignore')[:1200]
        return str(payload)[:1200]

    @staticmethod
    def _decode_header(value: str) -> str:
        parts = decode_header(value)
        decoded = []
        for text, encoding in parts:
            if isinstance(text, bytes):
                decoded.append(text.decode(encoding or 'utf-8', errors='ignore'))
            else:
                decoded.append(text)
        return ''.join(decoded)
