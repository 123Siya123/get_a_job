from __future__ import annotations

from typing import Any
from urllib.parse import quote

from playwright.async_api import BrowserContext, Page, async_playwright

from jobapplyer.config import AppSettings


class BrowserSession:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self._playwright = None
        self.context: BrowserContext | None = None
        self.pages: dict[str, Page] = {}

    async def start(self) -> None:
        if self.context:
            return
        self._playwright = await async_playwright().start()
        self.context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.settings.browser_user_data_dir),
            headless=self.settings.browser_headless,
            channel=self.settings.browser_channel,
            viewport={
                'width': self.settings.browser_viewport_width,
                'height': self.settings.browser_viewport_height,
            },
            accept_downloads=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        await self.ensure_tabs()

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
            self.context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self.pages = {}

    async def ensure_tabs(self) -> dict[str, Page]:
        if not self.context:
            raise RuntimeError('BrowserSession.start() must be called first.')
        targets = {
            'jobs': self.settings.job_tab_start_url,
            'gmail': self.settings.gmail_url,
            'tracker': self.settings.tracker_tab_url,
        }
        for name, url in targets.items():
            page = self.pages.get(name)
            if not page or page.is_closed():
                page = await self.context.new_page()
                self.pages[name] = page
            if url and (page.url in {'about:blank', ''} or name == 'tracker'):
                try:
                    await page.goto(url, wait_until='domcontentloaded')
                except Exception:
                    if name == 'tracker':
                        pass
                    else:
                        raise
        return self.pages

    def page(self, name: str) -> Page:
        if name not in self.pages:
            raise KeyError(f'Unknown browser tab: {name}')
        return self.pages[name]

    async def draft_gmail(self, *, to: str, subject: str, body: str, attachment: str = '', auto_send: bool = False) -> dict[str, Any]:
        gmail = self.page('gmail')
        compose_url = (
            'https://mail.google.com/mail/?view=cm&fs=1'
            f'&to={quote(to)}&su={quote(subject)}&body={quote(body)}'
        )
        await gmail.goto(compose_url, wait_until='domcontentloaded')
        await gmail.wait_for_timeout(1500)
        if attachment:
            file_input = gmail.locator('input[type="file"]').first
            if await file_input.count():
                await file_input.set_input_files(attachment)
                await gmail.wait_for_timeout(1500)
        if auto_send:
            send_button = gmail.locator('div[role="button"][data-tooltip^="Send"], div[role="button"][aria-label*="Send"]').first
            if await send_button.count():
                await send_button.click()
                return {'mode': 'gmail', 'status': 'sent'}
        return {'mode': 'gmail', 'status': 'drafted'}
