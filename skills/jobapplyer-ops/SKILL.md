---
name: jobapplyer-ops
description: Maintain or extend the local Jobapplyer browser agent, dashboard, discovery logic, adapters, and tracking pipeline.
---

# Jobapplyer Ops

Use this skill when the task is to improve, debug, or operate the Jobapplyer system in this repo.

## Quick map

- App config: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/config.py`
- Browser runtime: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/browser/session.py`
- Generic apply flow: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/browser/generic_apply.py`
- Form filling logic: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/browser/forms.py`
- Discovery: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/services/discovery.py`
- Orchestration loop: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/services/orchestrator.py`
- Gmail tracking: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/integrations/gmail.py`
- Sheet export and sync: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/integrations/sheets.py`
- Dashboard: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/web.py`
- Candidate config: `C:/Users/Siya/Desktop/Projects/Jobapplyer/config/candidate_profile.json`
- Search config: `C:/Users/Siya/Desktop/Projects/Jobapplyer/config/search_preferences.json`
- Target companies: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/data/companies.json`

## Workflow

1. Check runtime settings first.
2. Keep the dedicated browser profile stable unless the user explicitly wants to attach a personal one.
3. Prefer deterministic selector updates over adding more LLM calls.
4. If a site fails repeatedly, add or improve a site-specific adapter instead of making the generic flow looser.
5. Preserve safe defaults: `AUTO_SUBMIT=false` should remain the default unless the user asks otherwise.
6. Keep `runtime/applications.csv` and the dashboard in sync after major tracking changes.

## Guardrails

- Never hardcode live secrets into repo files.
- Do not silently enable full auto-submit after changing browser logic.
- Treat Gmail and sheet access as optional integrations; the local dashboard is the fallback control plane.
- Log important state changes to the events table so the dashboard stays explainable.
