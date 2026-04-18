from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    discovered = 'discovered'
    queued = 'queued'
    applying = 'applying'
    ready_for_review = 'ready_for_review'
    applied = 'applied'
    in_review = 'in_review'
    interview = 'interview'
    declined = 'declined'
    offer = 'offer'
    accepted = 'accepted'
    needs_action = 'needs_action'
    blocked = 'blocked'


class CandidateProfile(BaseModel):
    first_name: str = ''
    last_name: str = ''
    email: str = ''
    phone: str = ''
    city: str = ''
    country: str = ''
    postal_code: str = ''
    address_line: str = ''
    linkedin_url: str = ''
    github_url: str = ''
    portfolio_url: str = ''
    university: str = ''
    degree_program: str = ''
    graduation_date: str = ''
    summary: str = ''
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    authorized_to_work_in_germany: bool | None = None
    need_visa_sponsorship: bool | None = None
    available_from: str = ''
    desired_salary_eur_monthly: str = ''
    resume_path: str = ''
    cover_letter_path: str = ''
    cover_letter_template: str = ''

    @property
    def full_name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip()

    def resume_file(self) -> Path | None:
        if not self.resume_path:
            return None
        return Path(self.resume_path)

    def cover_letter_file(self) -> Path | None:
        if not self.cover_letter_path:
            return None
        return Path(self.cover_letter_path)

    def ready_for_auto_apply(self) -> bool:
        resume = self.resume_file()
        return bool(
            self.first_name
            and self.last_name
            and self.email
            and self.phone
            and resume
            and resume.exists()
        )


class SearchPreferences(BaseModel):
    roles: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    sectors: list[str] = Field(default_factory=list)
    preferred_languages: list[str] = Field(default_factory=list)
    minimum_score: float = 0.62
    prestige_bias: bool = True
    max_company_visits_per_cycle: int = 8


class CompanyTarget(BaseModel):
    name: str
    sector: str
    careers_url: str
    location_hint: str = ''
    prestige: float = 0.75
    tags: list[str] = Field(default_factory=list)
    notes: str = ''


class JobOpportunity(BaseModel):
    id: str
    company: str
    title: str
    source_url: str
    apply_url: str
    location: str = ''
    sector: str = ''
    discovered_at: str
    score: float = 0.0
    score_reason: str = ''
    snippet: str = ''
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApplicationRecord(BaseModel):
    id: str
    job_id: str
    company: str
    title: str
    status: ApplicationStatus = ApplicationStatus.discovered
    source_url: str
    apply_url: str
    outreach_channel: str = 'browser'
    last_event_at: str
    notes: str = ''
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSnapshot(BaseModel):
    running: bool = False
    current_stage: str = 'idle'
    current_company: str = ''
    current_job: str = ''
    last_cycle_at: str = ''
    last_cycle_summary: str = ''
