from __future__ import annotations

from pypdf import PdfReader

from jobapplyer.config import AppSettings
from jobapplyer.models import CandidateProfile, CompanyTarget, SearchPreferences
from jobapplyer.utils import load_json_file


def load_candidate_profile(settings: AppSettings) -> CandidateProfile:
    source = settings.candidate_profile_path
    if not source.exists():
        source = settings.candidate_profile_example_path
    payload = load_json_file(source, default={}) or {}
    return CandidateProfile.model_validate(payload)


def load_search_preferences(settings: AppSettings) -> SearchPreferences:
    payload = load_json_file(settings.search_preferences_path, default={}) or {}
    return SearchPreferences.model_validate(payload)


def load_companies(settings: AppSettings) -> list[CompanyTarget]:
    payload = load_json_file(settings.companies_path, default=[]) or []
    return [CompanyTarget.model_validate(item) for item in payload]


def extract_resume_text(profile: CandidateProfile) -> str:
    resume_path = profile.resume_file()
    if not resume_path or not resume_path.exists():
        return ''
    if resume_path.suffix.lower() != '.pdf':
        return ''
    try:
        reader = PdfReader(str(resume_path))
        parts: list[str] = []
        for page in reader.pages[:5]:
            parts.append(page.extract_text() or '')
        return '\n'.join(part for part in parts if part).strip()
    except Exception:
        return ''
