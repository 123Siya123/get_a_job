from __future__ import annotations

from playwright.async_api import Page

from jobapplyer.browser.forms import fill_visible_form
from jobapplyer.browser.session import BrowserSession
from jobapplyer.config import AppSettings
from jobapplyer.llm.router import LLMRouter
from jobapplyer.models import CandidateProfile, JobOpportunity


APPLY_SELECTORS = [
    'text=/apply now/i',
    'text=/apply for this job/i',
    'text=/apply/i',
    'text=/bewerben/i',
    'text=/jetzt bewerben/i',
    'a[href*="apply"]',
    'a[href*="jobs.lever.co"]',
    'a[href*="greenhouse.io"]',
]

SUBMIT_SELECTORS = [
    'button:has-text("Submit")',
    'button:has-text("Send application")',
    'button:has-text("Bewerbung absenden")',
    'input[type="submit"]',
]


class GenericApplicationAgent:
    def __init__(
        self,
        settings: AppSettings,
        browser: BrowserSession,
        llm: LLMRouter,
    ):
        self.settings = settings
        self.browser = browser
        self.llm = llm

    async def apply(self, job: JobOpportunity, profile: CandidateProfile) -> dict:
        page = self.browser.page('jobs')
        await page.goto(job.apply_url or job.source_url, wait_until='domcontentloaded')
        await page.wait_for_timeout(1500)

        page = await self._maybe_open_apply_surface(page)
        form_summary = await fill_visible_form(page, profile, job.company, job.title, self.llm)

        if form_summary['field_count'] == 0:
            email_address = await self._extract_contact_email(page)
            if email_address and self.settings.allow_email_fallback:
                body = profile.cover_letter_template.format(company=job.company, title=job.title, sector=job.sector or 'the sector') if profile.cover_letter_template else profile.summary
                email_result = await self.browser.draft_gmail(
                    to=email_address,
                    subject=f'Application: {job.title}',
                    body=body,
                    attachment=str(profile.resume_file()) if profile.resume_file() else '',
                    auto_send=self.settings.auto_submit,
                )
                return {
                    'status': 'applied' if email_result['status'] == 'sent' else 'ready_for_review',
                    'mode': 'email_fallback',
                    'details': email_result,
                    'form_summary': form_summary,
                }
            return {
                'status': 'blocked',
                'mode': 'no_form_found',
                'details': {'url': page.url},
                'form_summary': form_summary,
            }

        if form_summary['missing_required']:
            return {
                'status': 'needs_action',
                'mode': 'form',
                'details': {'missing_required': form_summary['missing_required']},
                'form_summary': form_summary,
            }

        if self.settings.auto_submit:
            submitted = await self._submit(page)
            return {
                'status': 'applied' if submitted else 'ready_for_review',
                'mode': 'form',
                'details': {'submitted': submitted},
                'form_summary': form_summary,
            }

        return {
            'status': 'ready_for_review',
            'mode': 'form',
            'details': {'submitted': False},
            'form_summary': form_summary,
        }

    async def _maybe_open_apply_surface(self, page: Page) -> Page:
        existing_pages = set(self.browser.context.pages if self.browser.context else [])
        for selector in APPLY_SELECTORS:
            locator = page.locator(selector).first
            if await locator.count():
                try:
                    await locator.click(timeout=2500)
                    await page.wait_for_timeout(2000)
                except Exception:
                    continue
                if self.browser.context:
                    new_pages = [item for item in self.browser.context.pages if item not in existing_pages]
                    if new_pages:
                        return new_pages[-1]
                return page
        return page

    async def _submit(self, page: Page) -> bool:
        for selector in SUBMIT_SELECTORS:
            locator = page.locator(selector).first
            if await locator.count():
                try:
                    await locator.click()
                    await page.wait_for_timeout(2500)
                    return True
                except Exception:
                    continue
        return False

    async def _extract_contact_email(self, page: Page) -> str:
        content = await page.content()
        for token in content.replace('"', ' ').replace("'", ' ').split():
            if '@' in token and '.' in token:
                cleaned = token.strip('>);,[]()')
                if cleaned.count('@') == 1:
                    return cleaned
        return ''
