from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import Page

from jobapplyer.llm.router import LLMRouter
from jobapplyer.models import CandidateProfile


FORM_FIELDS_SCRIPT = r'''
() => {
  const nodes = Array.from(document.querySelectorAll('input, textarea, select')).filter((el) => {
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image'].includes(type)) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  });

  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();

  const labelFor = (el) => {
    if (el.id) {
      const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (label) return clean(label.textContent);
    }
    const wrapped = el.closest('label');
    if (wrapped) return clean(wrapped.textContent);
    const group = el.closest('[data-testid], fieldset, form, div, li, section');
    if (!group) return '';
    const labelCandidate = group.querySelector('label, legend, span, p, strong');
    return labelCandidate ? clean(labelCandidate.textContent) : '';
  };

  return nodes.map((el, index) => {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || tag).toLowerCase();
    const options = tag === 'select' ? Array.from(el.options).map((item) => clean(item.textContent)) : [];
    return {
      index,
      tag,
      type,
      id: el.id || '',
      name: el.getAttribute('name') || '',
      label: labelFor(el),
      placeholder: el.getAttribute('placeholder') || '',
      required: Boolean(el.required || el.getAttribute('aria-required') === 'true'),
      options,
      accept: el.getAttribute('accept') || ''
    };
  });
}
'''


@dataclass
class FieldDecision:
    value: str = ''
    should_check: bool = False
    note: str = ''


def _signature(field: dict[str, Any]) -> str:
    parts = [field.get('label', ''), field.get('name', ''), field.get('placeholder', ''), field.get('type', '')]
    return ' '.join(part for part in parts if part).lower()


def _string_value(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, list):
        return ', '.join(str(item) for item in value if item)
    return str(value)


def guess_builtin_value(field: dict[str, Any], profile: CandidateProfile, company: str, job_title: str) -> FieldDecision:
    signature = _signature(field)
    resume_path = profile.resume_file()
    cover_letter_path = profile.cover_letter_file()

    direct_map = [
        (['first name', 'vorname'], profile.first_name),
        (['last name', 'surname', 'nachname'], profile.last_name),
        (['full name', 'name'], profile.full_name),
        (['email', 'e-mail'], profile.email),
        (['phone', 'mobile', 'telefon'], profile.phone),
        (['linkedin'], profile.linkedin_url),
        (['github'], profile.github_url),
        (['portfolio', 'website'], profile.portfolio_url),
        (['city', 'ort'], profile.city),
        (['country', 'land'], profile.country),
        (['postal code', 'zip', 'post code'], profile.postal_code),
        (['address', 'street'], profile.address_line),
        (['university', 'hochschule'], profile.university),
        (['degree', 'study', 'course'], profile.degree_program),
        (['graduation', 'abschluss'], profile.graduation_date),
        (['availability', 'start date', 'available from'], profile.available_from),
        (['salary', 'compensation', 'gehalt'], profile.desired_salary_eur_monthly),
        (['skills', 'technologies'], profile.skills),
        (['language', 'sprach'], profile.languages),
    ]
    for terms, value in direct_map:
        if any(term in signature for term in terms):
            return FieldDecision(value=_string_value(value), note='builtin')

    if 'resume' in signature or 'cv' in signature or 'lebenslauf' in signature:
        if resume_path and resume_path.exists():
            return FieldDecision(value=str(resume_path), note='resume-file')
    if 'cover letter' in signature or 'anschreiben' in signature:
        if cover_letter_path and cover_letter_path.exists():
            return FieldDecision(value=str(cover_letter_path), note='cover-letter-file')
        if profile.cover_letter_template:
            return FieldDecision(
                value=profile.cover_letter_template.format(company=company, title=job_title, sector='the company sector'),
                note='cover-letter-template',
            )

    if any(term in signature for term in ['authorized', 'work permit', 'arbeitserlaubnis']):
        return FieldDecision(value='Yes' if profile.authorized_to_work_in_germany else 'No', note='work-auth')
    if any(term in signature for term in ['visa', 'sponsorship']):
        return FieldDecision(value='Yes' if profile.need_visa_sponsorship else 'No', note='visa')
    if any(term in signature for term in ['privacy', 'datenschutz', 'terms', 'consent']):
        return FieldDecision(should_check=True, note='consent-checkbox')
    return FieldDecision()


async def fill_visible_form(
    page: Page,
    profile: CandidateProfile,
    company: str,
    job_title: str,
    llm: LLMRouter | None = None,
) -> dict[str, Any]:
    fields = await page.evaluate(FORM_FIELDS_SCRIPT)
    locators = page.locator('input, textarea, select')
    filled: list[str] = []
    skipped: list[str] = []
    missing_required: list[str] = []

    for field in fields:
        signature = _signature(field)
        decision = guess_builtin_value(field, profile, company, job_title)
        if not decision.value and not decision.should_check and llm and field.get('required'):
            generated = await llm.answer_application_question(
                company=company,
                job_title=job_title,
                field_label=field.get('label') or field.get('name') or signature,
                profile=profile,
            )
            if generated:
                decision = FieldDecision(value=generated, note='llm')

        locator = locators.nth(int(field['index']))
        field_label = field.get('label') or field.get('name') or field.get('type')

        if field['type'] == 'file' and decision.value:
            file_path = Path(decision.value)
            if file_path.exists():
                await locator.set_input_files(str(file_path))
                filled.append(f'{field_label} -> file')
                continue

        if decision.should_check and field['type'] == 'checkbox':
            try:
                await locator.check(force=True)
                filled.append(f'{field_label} -> checked')
            except Exception:
                skipped.append(f'{field_label} (checkbox failed)')
            continue

        if field['tag'] == 'select' and decision.value:
            options = [option.lower() for option in field.get('options', [])]
            candidate = decision.value.strip().lower()
            selected = None
            for option in options:
                if candidate and candidate in option:
                    selected = option
                    break
            if not selected and options:
                selected = next((option for option in options if option not in {'select', 'please choose'}), options[0])
            if selected:
                try:
                    await locator.select_option(label=selected)
                    filled.append(f'{field_label} -> {selected}')
                    continue
                except Exception:
                    skipped.append(f'{field_label} (select failed)')

        if decision.value:
            try:
                await locator.fill(decision.value)
                filled.append(f'{field_label} -> {decision.note}')
                continue
            except Exception:
                skipped.append(f'{field_label} (fill failed)')
                continue

        if field.get('required'):
            missing_required.append(field_label)
        else:
            skipped.append(field_label)

    return {
        'field_count': len(fields),
        'filled': filled,
        'skipped': skipped,
        'missing_required': missing_required,
    }
