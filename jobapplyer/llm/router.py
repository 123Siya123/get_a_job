from __future__ import annotations

from typing import Any

from jobapplyer.config import AppSettings
from jobapplyer.llm.gemini import GeminiClientPool
from jobapplyer.models import CandidateProfile, SearchPreferences
from jobapplyer.utils import compact_text


class LLMRouter:
    def __init__(self, settings: AppSettings, resume_text: str = ''):
        self.settings = settings
        self.resume_text = compact_text(resume_text, limit=2200)
        self.gemini = GeminiClientPool(settings)

    @property
    def enabled(self) -> bool:
        return self.gemini.enabled

    async def close(self) -> None:
        await self.gemini.close()

    async def refine_job_score(
        self,
        *,
        company: str,
        title: str,
        sector: str,
        snippet: str,
        preferences: SearchPreferences,
        baseline_score: float,
    ) -> tuple[float, str]:
        if not self.enabled:
            return baseline_score, 'Heuristic score only.'
        prompt = f'''
Score this job from 0.0 to 1.0 for a mechatronics student looking for internships or working student roles.

Company: {company}
Sector: {sector}
Title: {title}
Snippet: {compact_text(snippet, 800)}
Target roles: {preferences.roles}
Keywords: {preferences.keywords}
Locations: {preferences.locations}
Baseline score: {baseline_score}

Return JSON with keys: score, reason, apply_now.
'''
        payload = await self.gemini.generate_json(
            prompt,
            self.settings.gemini_planner_model,
            system_instruction='Be conservative. Prefer rejecting non-student or senior roles. Return compact JSON only.',
        )
        score = float(payload.get('score', baseline_score))
        reason = str(payload.get('reason', 'LLM refinement.'))
        return max(0.0, min(score, 1.0)), reason

    async def answer_application_question(
        self,
        *,
        company: str,
        job_title: str,
        field_label: str,
        profile: CandidateProfile,
    ) -> str:
        if not self.enabled:
            return ''
        prompt = f'''
Draft a short application-form answer.
Company: {company}
Job title: {job_title}
Question / label: {field_label}
Candidate summary: {profile.summary}
Candidate skills: {profile.skills}
Candidate university: {profile.university}
Candidate degree: {profile.degree_program}
Candidate availability: {profile.available_from}
Resume excerpt: {self.resume_text}

Rules:
- Keep the answer under 450 characters.
- Do not invent facts.
- If the question asks for unavailable personal data, return an empty string.
- Return plain text only.
'''
        return (await self.gemini.generate_text(prompt, self.settings.gemini_browser_model)).strip()

    async def classify_inbound_message(self, *, sender: str, subject: str, snippet: str) -> dict[str, Any]:
        if not self.enabled:
            return {}
        prompt = f'''
Classify this recruiting email.
Sender: {sender}
Subject: {subject}
Snippet: {compact_text(snippet, 1000)}

Return JSON with keys: status, confidence, reason.
Allowed statuses: in_review, interview, declined, offer, needs_action.
'''
        return await self.gemini.generate_json(
            prompt,
            self.settings.gemini_classifier_model,
            system_instruction='Return compact JSON only. Use needs_action for tests, assessments, scheduling, or requests for documents.',
        )
