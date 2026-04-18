from __future__ import annotations

from urllib.parse import urlparse

from jobapplyer.browser.session import BrowserSession
from jobapplyer.llm.router import LLMRouter
from jobapplyer.models import CompanyTarget, JobOpportunity, SearchPreferences
from jobapplyer.utils import compact_text, slugify, utcnow_iso


DISCOVERY_SCRIPT = r'''
() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const anchors = Array.from(document.querySelectorAll('a[href]'));
  return anchors.map((anchor) => {
    const card = anchor.closest('article, li, div, section') || anchor.parentElement;
    return {
      href: anchor.href,
      text: clean(anchor.textContent),
      snippet: clean(card ? card.textContent : '')
    };
  }).filter((item) => item.href && item.text);
}
'''


class JobDiscoveryService:
    def __init__(self, browser: BrowserSession, llm: LLMRouter):
        self.browser = browser
        self.llm = llm

    async def discover(self, companies: list[CompanyTarget], preferences: SearchPreferences) -> list[JobOpportunity]:
        page = self.browser.page('jobs')
        opportunities: list[JobOpportunity] = []
        visited = 0

        for company in companies[: preferences.max_company_visits_per_cycle]:
            visited += 1
            await page.goto(company.careers_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2500)
            for btn_text in ["Accept", "Accept All", "Akzeptieren", "Alle akzeptieren", "Allow", "Agree", "I agree", "Zustimmen"]:
                try:
                    locator = page.locator(f'button:has-text("{btn_text}")').first
                    if await locator.count() > 0:
                        await locator.click(timeout=1000)
                        await page.wait_for_timeout(1500)
                        break
                except Exception:
                    pass
            extracted = await page.evaluate(DISCOVERY_SCRIPT)
            for entry in extracted:
                url = entry['href']
                title = compact_text(entry['text'], 180)
                snippet = compact_text(entry.get('snippet', ''), 400)
                baseline_score, baseline_reason = self._heuristic_score(company, title, snippet, preferences)
                if baseline_score < max(0.35, preferences.minimum_score - 0.18):
                    continue
                score, reason = baseline_score, baseline_reason
                if self.llm.enabled and baseline_score >= 0.45:
                    score, reason = await self.llm.refine_job_score(
                        company=company.name,
                        title=title,
                        sector=company.sector,
                        snippet=snippet,
                        preferences=preferences,
                        baseline_score=baseline_score,
                    )
                if score < preferences.minimum_score:
                    continue
                opportunities.append(
                    JobOpportunity(
                        id=slugify(f'{company.name}-{title}-{url}'),
                        company=company.name,
                        title=title,
                        source_url=url,
                        apply_url=url,
                        location=company.location_hint,
                        sector=company.sector,
                        discovered_at=utcnow_iso(),
                        score=round(score, 3),
                        score_reason=reason,
                        snippet=snippet,
                        metadata={'visited_company_page': company.careers_url, 'visited_count': visited},
                    )
                )
        deduped: dict[str, JobOpportunity] = {}
        for opportunity in opportunities:
            deduped[opportunity.source_url] = opportunity
        return sorted(deduped.values(), key=lambda item: item.score, reverse=True)

    @staticmethod
    def _heuristic_score(company: CompanyTarget, title: str, snippet: str, preferences: SearchPreferences) -> tuple[float, str]:
        blob = f'{title} {snippet} {company.sector} {company.location_hint}'.lower()
        score = 0.0
        reasons: list[str] = []
        if any(term in blob for term in ['intern', 'internship', 'praktikum']):
            score += 0.34
            reasons.append('internship term')
        if any(term in blob for term in ['working student', 'werkstudent', 'student worker']):
            score += 0.38
            reasons.append('working-student term')
        keyword_hits = [term for term in preferences.keywords if term.lower() in blob]
        if keyword_hits:
            score += min(0.26, 0.06 * len(keyword_hits))
            reasons.append(f'keywords: {", ".join(keyword_hits[:4])}')
        location_hits = [term for term in preferences.locations if term.lower() in blob]
        if location_hits:
            score += 0.12
            reasons.append(f'location: {location_hits[0]}')
        if preferences.prestige_bias:
            score += min(company.prestige * 0.16, 0.16)
            reasons.append('prestige bias')
        if any(term in blob for term in ['senior', 'lead', 'manager', 'director', 'principal']):
            score -= 0.45
            reasons.append('seniority penalty')
        if not any(term in blob for term in ['intern', 'internship', 'praktikum', 'working student', 'werkstudent', 'student worker']):
            score -= 0.15
            reasons.append('not obviously student-friendly')
        domain = urlparse(company.careers_url).netloc
        reasons.append(domain)
        return max(0.0, min(score, 1.0)), '; '.join(reasons)
