from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=('.env', '.env.local'), extra='ignore')

    app_name: str = 'Jobapplyer'
    runtime_dir: Path = Path('runtime')
    database_path: Path = Path('runtime/jobapplyer.db')
    export_dir: Path = Path('runtime/exports')
    log_dir: Path = Path('runtime/logs')

    ai_provider: str = Field(default='gemini', validation_alias='AI_PROVIDER')
    local_model_url: str = Field(default='http://127.0.0.1:1234/v1', validation_alias='LOCAL_MODEL_URL')
    local_model_name: str = Field(default='google/gemma-4-e2b', validation_alias='LOCAL_MODEL_NAME')

    gemini_api_keys_raw: str = Field(default='', validation_alias='GEMINI_API_KEYS')
    gemini_planner_model: str = Field(default='gemini-3.1-flash-lite-preview', validation_alias='GEMINI_PLANNER_MODEL')
    gemini_browser_model: str = Field(default='gemini-3-flash-preview', validation_alias='GEMINI_BROWSER_MODEL')
    gemini_classifier_model: str = Field(default='gemini-3.1-flash-lite-preview', validation_alias='GEMINI_CLASSIFIER_MODEL')
    gemini_same_key_retries: int = Field(default=2, validation_alias='GEMINI_SAME_KEY_RETRIES')
    gemini_retry_backoff_seconds: float = Field(default=5.0, validation_alias='GEMINI_RETRY_BACKOFF_SECONDS')

    browser_headless: bool = Field(default=False, validation_alias='BROWSER_HEADLESS')
    browser_channel: str | None = Field(default=None, validation_alias='BROWSER_CHANNEL')
    browser_user_data_dir: Path = Field(default=Path('runtime/browser-profile'), validation_alias='BROWSER_USER_DATA_DIR')
    browser_viewport_width: int = 1440
    browser_viewport_height: int = 900

    auto_submit: bool = Field(default=False, validation_alias='AUTO_SUBMIT')
    auto_start_agent: bool = Field(default=False, validation_alias='AUTO_START_AGENT')
    run_interval_seconds: int = Field(default=900, validation_alias='RUN_INTERVAL_SECONDS')
    max_companies_per_cycle: int = Field(default=8, validation_alias='MAX_COMPANIES_PER_CYCLE')
    max_jobs_per_cycle: int = Field(default=15, validation_alias='MAX_JOBS_PER_CYCLE')
    max_applications_per_cycle: int = Field(default=2, validation_alias='MAX_APPLICATIONS_PER_CYCLE')

    job_tab_start_url: str = Field(
        default='https://www.stepstone.de/en/jobs/internship/mechatronics/in-frankfurt-am-main',
        validation_alias='JOB_TAB_START_URL',
    )
    gmail_url: str = Field(default='https://mail.google.com/mail/u/0/#inbox', validation_alias='GMAIL_URL')
    gmail_inbox_query: str = Field(default='newer_than:14d', validation_alias='GMAIL_INBOX_QUERY')
    tracker_url: str = Field(default='', validation_alias='TRACKER_URL')

    candidate_profile_path: Path = Path('config/candidate_profile.json')
    candidate_profile_example_path: Path = Path('config/candidate_profile.example.json')
    search_preferences_path: Path = Path('config/search_preferences.json')
    companies_path: Path = Path('jobapplyer/data/companies.json')

    gmail_address: str = Field(default='', validation_alias='GMAIL_ADDRESS')
    gmail_app_password: str = Field(default='', validation_alias='GMAIL_APP_PASSWORD')
    gmail_imap_host: str = Field(default='imap.gmail.com', validation_alias='GMAIL_IMAP_HOST')

    google_sheet_id: str = Field(default='', validation_alias='GOOGLE_SHEET_ID')
    google_sheet_name: str = Field(default='Applications', validation_alias='GOOGLE_SHEET_NAME')
    google_service_account_file: str = Field(default='', validation_alias='GOOGLE_SERVICE_ACCOUNT_FILE')

    allow_email_fallback: bool = Field(default=True, validation_alias='ALLOW_EMAIL_FALLBACK')

    @property
    def gemini_api_keys(self) -> list[str]:
        value = self.gemini_api_keys_raw
        if not value:
            return []
        if isinstance(value, list):
            return [item.strip() for item in value if item and isinstance(item, str) and item.strip()]
        return [item.strip() for item in value.split(',') if item.strip()]

    @field_validator('browser_channel', mode='before')
    @classmethod
    def parse_browser_channel(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    def ensure_directories(self) -> None:
        for path in [self.runtime_dir, self.export_dir, self.log_dir, self.browser_user_data_dir.parent]:
            Path(path).mkdir(parents=True, exist_ok=True)
        self.browser_user_data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def tracker_tab_url(self) -> str:
        if self.tracker_url:
            return self.tracker_url
        if self.google_sheet_id:
            return f'https://docs.google.com/spreadsheets/d/{self.google_sheet_id}'
        return 'http://127.0.0.1:8000/'

    def gmail_imap_enabled(self) -> bool:
        return bool(self.gmail_address and self.gmail_app_password)

    def sheets_enabled(self) -> bool:
        return bool(self.google_sheet_id and self.google_service_account_file)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.ensure_directories()
    return settings
