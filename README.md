# Jobapplyer

A local browser-agent application for discovering internships and working-student jobs, filling web application forms, drafting fallback emails, tracking company replies from Gmail, and mirroring the pipeline into a dashboard plus CSV or Google Sheets.

## What I Built

- A local FastAPI dashboard at `http://127.0.0.1:8000`
- A Playwright browser runtime that keeps 3 tabs open:
  - a current job page
  - Gmail
  - your tracker tab (`Google Sheets` if configured, otherwise the local dashboard)
- A Gemini key pool with retry-first and rotate-after behavior
- A discovery loop that scans target company career pages and scores roles for your profile
- A generic form filler with resume upload, common field mapping, and LLM fallback for free-text questions
- Gmail IMAP status tracking for replies like rejection, interview, offer, and requests for action
- CSV export to `runtime/exports/applications.csv` and optional Google Sheets sync
- A companion Codex skill at `C:/Users/Siya/Desktop/Projects/Jobapplyer/skills/jobapplyer-ops/SKILL.md`

## Cheapest Practical Runtime

### Recommendation

The cheapest realistic setup for this project is:

1. Run the browser locally on your Windows PC with Playwright.
2. Use Gemini as the planner and question-answering model.
3. Keep Gmail tracking on IMAP or Gmail web, and use Google Sheets only if you want cloud mirroring.
4. Leave `AUTO_SUBMIT=false` first, then switch to `true` only after a few supervised runs.

That is cheaper than running Codex as the live browser operator, and simpler than relying on OpenClaw for this exact workflow.

### Why not Codex as the runtime?

Codex is excellent for building and maintaining this app, but it is not the cheapest browser-control runtime.

- OpenAI's official `GPT-5.1 Codex` model page describes it as optimized for agentic coding in Codex, not as the cheapest general browser-control agent.
- OpenAI's pricing page currently shows `computer-use-preview` as a separate specialized model/tool category, which means browser-computer use is a different cost center from Codex itself.
- If you wanted an OpenAI-only runtime, you would more likely pair a general model with computer-use tooling, which is usually more expensive than a local Playwright flow plus Gemini Flash-class models.

### Why not OpenClaw as the first pick?

OpenClaw is a real option, especially if you want a prebuilt agent shell.

- Its browser docs say it can run a dedicated Chrome/Edge/Chromium profile the agent controls.
- It can also attach to your signed-in Chrome session through the built-in `user` profile.
- That said, for this exact project, a custom local app is cheaper and easier to keep deterministic because we can mix explicit selectors, DB tracking, Gmail parsing, and only selective LLM calls.

## Gemini Model Research

### Important correction

As of **April 18, 2026**, the official Google AI docs do **not** show a normal text model called simply `Gemini 3.1 Flash` for this use case.

What the official models page does show is:

- `Gemini 3 Flash Preview`
- `Gemini 3.1 Flash-Lite Preview`
- `Gemini 3.1 Pro Preview`
- `Gemini 3.1 Flash Live Preview`
- `Gemini 3.1 Flash TTS Preview`

So for this app:

- Use `gemini-3.1-flash-lite-preview` for cheap routing, scoring, and question answering.
- Upgrade selected harder steps to `gemini-3-flash-preview` if needed.
- Only use `gemini-2.5-computer-use-preview-10-2025` if you specifically want screenshot-driven computer use. It is powerful, but it is not the cheapest path.

### Why the built-in key rotator may not save you by itself

Google's official rate-limit docs say Gemini rate limits are applied **per project, not per API key**.

That means:

- If all your keys belong to the same Google project, rotation does not increase your quota.
- If your keys belong to different projects, rotation can help.
- This app still retries the same key first and then rotates, because that is useful when one key or project is temporarily constrained.

## Cost Snapshot

### Cheapest path here

- Local PC + Playwright: free
- FastAPI dashboard + SQLite + CSV export: free
- Gmail IMAP tracking: free
- Google Sheets sync: free, if you already have Google access and set up service-account sharing
- Gemini free tier: potentially free for light usage
- Heavy 24/7 autonomous usage: likely paid eventually

### Current pricing references

- Google pricing page shows `Gemini 3.1 Flash-Lite Preview` as a lower-cost Gemini 3 option than `Gemini 3 Flash Preview`.
- Google pricing also lists `Gemini 2.5 Computer Use Preview` separately, with no free tier shown for that model.
- OpenAI pricing shows Codex and computer-use as separate specialized categories.

## Safety Defaults

This repo intentionally starts in safer mode:

- `AUTO_SUBMIT=false`
- the app will discover and fill, but not blindly submit until you enable it
- secrets are not hardcoded into source files
- Gmail and Google Sheets are optional integrations, not hard dependencies

## Files You Will Care About

- App entry: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/main.py`
- Dashboard app: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/web.py`
- Orchestrator: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/services/orchestrator.py`
- Browser automation: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/browser/generic_apply.py`
- Form mapping: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/browser/forms.py`
- Discovery logic: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/services/discovery.py`
- Gemini router: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/llm/gemini.py`
- Search targets: `C:/Users/Siya/Desktop/Projects/Jobapplyer/jobapplyer/data/companies.json`
- Candidate template: `C:/Users/Siya/Desktop/Projects/Jobapplyer/config/candidate_profile.example.json`
- Search preferences: `C:/Users/Siya/Desktop/Projects/Jobapplyer/config/search_preferences.json`
- Start script: `C:/Users/Siya/Desktop/Projects/Jobapplyer/start.ps1`

## Setup

1. Edit `C:/Users/Siya/Desktop/Projects/Jobapplyer/config/candidate_profile.json` and replace the placeholder data with your real information.
2. Create `C:/Users/Siya/Desktop/Projects/Jobapplyer/.env.local` from `C:/Users/Siya/Desktop/Projects/Jobapplyer/.env.example`.
3. Put fresh Gemini keys into `GEMINI_API_KEYS`.
4. Optionally add Gmail IMAP credentials and Google Sheets settings.
5. Run `C:/Users/Siya/Desktop/Projects/Jobapplyer/start.ps1`.

By default the app can use Playwright's bundled Chromium. If you want to point it at a local Chrome installation instead, set `BROWSER_CHANNEL=chrome` in `C:/Users/Siya/Desktop/Projects/Jobapplyer/.env.local`.

## Notes About Your Existing Gemini Keys

I did not bake the raw Gemini keys from the chat into repo files.

That was deliberate because:

- source-controlled secrets are easy to leak by accident
- Google quotas are per project, so copied keys do not automatically mean more usable quota
- if those keys have already been pasted around, rotating them is the safer move

## Current Limitations

- This is a strong local foundation, not a magical universal adapter for every career site on day one.
- Workday and other login-heavy ATS flows may need site-specific adapters.
- Gmail status tracking is robust with IMAP, but browser-only inbox tracking is not yet implemented.
- Google Sheets sync is implemented via service account, not by clicking cells in the browser.
- The generic form filler is conservative and will stop on missing required fields instead of inventing answers.

## Sources

- Google Gemini models: [https://ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
- Google Gemini pricing: [https://ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Google Gemini rate limits: [https://ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- Google Gemini computer use: [https://ai.google.dev/gemini-api/docs/computer-use](https://ai.google.dev/gemini-api/docs/computer-use)
- OpenAI GPT-5.1 Codex model page: [https://developers.openai.com/api/docs/models/gpt-5.1-codex](https://developers.openai.com/api/docs/models/gpt-5.1-codex)
- OpenAI pricing: [https://developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing)
- OpenClaw browser docs: [https://docs.openclaw.ai/tools/browser](https://docs.openclaw.ai/tools/browser)
- OpenClaw repository: [https://github.com/openclaw/openclaw](https://github.com/openclaw/openclaw)
