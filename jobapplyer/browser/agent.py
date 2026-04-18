"""
AI Browser Agent powered by browser-use.

Instead of hardcoded CSS selectors, this agent SEES the page,
REASONS about what it sees, and DECIDES what to do — like a human.

The browser window is VISIBLE so the user can watch and intervene.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from browser_use import Agent, Browser
from browser_use.browser.profile import BrowserProfile
from langchain_google_genai import ChatGoogleGenerativeAI

# browser-use expects LLMs to have .provider and .model attributes.
# ChatGoogleGenerativeAI doesn't expose .provider natively, so we patch it.
if not hasattr(ChatGoogleGenerativeAI, 'provider'):
    ChatGoogleGenerativeAI.provider = 'google'  # type: ignore[attr-defined]

from jobapplyer.config import AppSettings
from jobapplyer.models import CandidateProfile, SearchPreferences

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thought tracking
# ---------------------------------------------------------------------------

class AgentThought:
    """A single thought / action from the AI agent."""

    def __init__(self, step: int, thought: str, action: str = '', result: str = ''):
        self.step = step
        self.thought = thought
        self.action = action
        self.result = result
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            'step': self.step,
            'thought': self.thought,
            'action': self.action,
            'result': self.result,
            'timestamp': self.timestamp,
        }


# ---------------------------------------------------------------------------
# Browser Agent
# ---------------------------------------------------------------------------

class BrowserAgent:
    """Wraps browser-use Agent with Gemini to perform agentic browser tasks.

    Key features:
    - Opens a REAL, VISIBLE Chrome window on your desktop
    - Uses a persistent user-data-dir so logins (Gmail etc.) survive restarts
    - Streams every reasoning step to the dashboard in real-time
    - demo_mode=True highlights every element the AI interacts with
    """

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.thoughts: list[AgentThought] = []
        self._step_count = 0
        self._on_thought: Callable[[AgentThought], None] | None = None
        self._stop_requested = False
        self._browser: Browser | None = None

    # -- public API ----------------------------------------------------------

    def set_thought_callback(self, callback: Callable[[AgentThought], None]) -> None:
        """Register a callback that fires every time the agent has a new thought."""
        self._on_thought = callback

    def request_stop(self) -> None:
        """Ask the currently-running agent to stop at the next step boundary."""
        self._stop_requested = True

    def clear_thoughts(self) -> None:
        self.thoughts.clear()
        self._step_count = 0

    def get_recent_thoughts(self, limit: int = 50) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.thoughts[-limit:]]

    # -- LLM -----------------------------------------------------------------

    def _get_llm(self, key_index: int = 0):
        """Create a Gemini LLM instance using the rotating API keys."""
        keys = self.settings.gemini_api_keys
        if not keys:
            raise RuntimeError('No Gemini API keys configured in .env.local')
        key = keys[key_index % len(keys)]
        return ChatGoogleGenerativeAI(
            model=self.settings.gemini_browser_model,
            google_api_key=key,
            temperature=0.1,
        )

    # -- Browser profile (persistent, visible) --------------------------------

    def _make_browser_profile(self) -> BrowserProfile:
        """Create a BrowserProfile for a VISIBLE, persistent browser session."""
        user_data = Path(self.settings.browser_user_data_dir).resolve()
        user_data.mkdir(parents=True, exist_ok=True)

        return BrowserProfile(
            headless=False,                    # <<< VISIBLE window
            disable_security=True,
            user_data_dir=str(user_data),      # persists cookies / logins
            window_size={'width': 1280, 'height': 900},
            highlight_elements=True,           # show what the AI is looking at
        )

    # -- internal helpers ----------------------------------------------------

    def _record_thought(self, thought: str, action: str = '', result: str = '') -> None:
        self._step_count += 1
        t = AgentThought(self._step_count, thought, action, result)
        self.thoughts.append(t)
        if len(self.thoughts) > 200:
            self.thoughts = self.thoughts[-200:]
        if self._on_thought:
            self._on_thought(t)
        logger.info('Agent step %d: %s | %s', self._step_count, thought, action)

    def _on_step(self, state, agent_output, step_number: int) -> None:
        """Callback fired by browser-use after EVERY agent step.

        This is what makes the dashboard update live — it fires while the
        agent is still running, not only after the cycle finishes.
        """
        # Extract the agent's reasoning from its output
        thought_text = ''
        action_text = ''

        if agent_output:
            # agent_output has .current_state (AgentBrain) with .evaluation, .memory, .next_goal
            brain = getattr(agent_output, 'current_state', None)
            if brain:
                evaluation = getattr(brain, 'evaluation_previous_goal', '') or ''
                memory = getattr(brain, 'memory', '') or ''
                next_goal = getattr(brain, 'next_goal', '') or ''
                thought_text = next_goal or memory or evaluation
                action_text = evaluation

            # Extract the action the agent chose
            actions = getattr(agent_output, 'actions', [])
            if actions:
                action_strs = []
                for a in actions[:3]:
                    # Each action is a dict-like with keys like 'click_element', 'input_text', etc.
                    action_dict = a.model_dump(exclude_none=True, exclude_unset=True) if hasattr(a, 'model_dump') else {}
                    for k, v in action_dict.items():
                        if v is not None:
                            action_strs.append(f'{k}: {str(v)[:100]}')
                if action_strs:
                    action_text = ' | '.join(action_strs)

        self._record_thought(
            thought_text or f'Step {step_number}',
            action_text or 'processing...',
        )

    async def _should_stop(self) -> bool:
        """Called by browser-use to check if we should stop the agent."""
        return self._stop_requested

    # -- Main task methods ---------------------------------------------------

    async def search_and_apply(
        self,
        profile: CandidateProfile,
        preferences: SearchPreferences,
        search_url: str,
    ) -> dict[str, Any]:
        """
        Main agentic loop: Open a real browser, go to a job board,
        search for matching jobs, and apply to them one by one.
        """
        self.clear_thoughts()
        self._stop_requested = False
        self._record_thought('Starting job search cycle', f'Opening {search_url}')

        task_prompt = self._build_search_task(profile, preferences, search_url)
        results: dict[str, Any] = {'jobs_found': 0, 'applications_attempted': 0, 'errors': []}

        try:
            llm = self._get_llm(0)
            browser_profile = self._make_browser_profile()

            browser = Browser(browser_profile=browser_profile)
            self._browser = browser

            agent = Agent(
                task=task_prompt,
                llm=llm,
                browser=browser,
                max_actions_per_step=3,
                use_vision=True,
                demo_mode=True,                            # highlights clicks
                register_new_step_callback=self._on_step,  # LIVE thought streaming
                register_should_stop_callback=self._should_stop,
            )

            self._record_thought('Agent brain initialized with Gemini', 'Launching visible browser...')

            # Run — browser-use will open a REAL window and start navigating
            history = await agent.run(max_steps=40)

            self._record_thought(
                'Agent cycle completed',
                'Analyzing results',
                str(history.final_result())[:500] if history else 'No result returned',
            )

            if history:
                results['raw_result'] = str(history.final_result())[:2000]

        except Exception as exc:
            error_msg = f'{type(exc).__name__}: {exc}'
            self._record_thought('Error during agent execution', 'Handling error', error_msg)
            results['errors'].append(error_msg)
            logger.exception('Browser agent error')
        finally:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

        return results

    async def apply_to_single_job(
        self,
        profile: CandidateProfile,
        job_url: str,
        company: str,
        job_title: str,
    ) -> dict[str, Any]:
        """Apply to a specific job URL using the AI agent."""
        self._stop_requested = False
        self._record_thought(f'Applying to {company}: {job_title}', f'Opening {job_url}')

        task_prompt = self._build_apply_task(profile, job_url, company, job_title)

        try:
            llm = self._get_llm(0)
            browser_profile = self._make_browser_profile()
            browser = Browser(browser_profile=browser_profile)
            self._browser = browser

            agent = Agent(
                task=task_prompt,
                llm=llm,
                browser=browser,
                max_actions_per_step=3,
                use_vision=True,
                demo_mode=True,
                register_new_step_callback=self._on_step,
                register_should_stop_callback=self._should_stop,
            )

            history = await agent.run(max_steps=30)

            self._record_thought(
                f'Finished application attempt for {company}',
                'Checking result',
                str(history.final_result())[:500] if history else 'Done',
            )

            return {
                'status': 'applied' if history else 'ready_for_review',
                'mode': 'browser_agent',
                'details': str(history.final_result())[:1000] if history else '',
            }

        except Exception as exc:
            self._record_thought(f'Error applying to {company}', str(exc))
            return {'status': 'blocked', 'mode': 'browser_agent_error', 'details': str(exc)}
        finally:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

    async def check_gmail(self, gmail_url: str) -> dict[str, Any]:
        """Check Gmail for application responses."""
        self._stop_requested = False
        self._record_thought('Checking Gmail for application responses', f'Opening {gmail_url}')

        task_prompt = f"""
Go to {gmail_url}.

If there is a cookie consent or login wall, handle it appropriately.
If already logged in, look through the inbox for emails related to job applications.

Look for emails from companies about:
- Application received confirmations
- Interview invitations
- Rejection notices
- Next steps or assessments

For each relevant email found, extract:
- Company name
- Job title (if mentioned)
- Status: one of "in_review", "interview", "declined", "offer", "needs_action"
- Brief summary

Return the results as a JSON array.
If no relevant emails are found, return an empty array.
"""

        try:
            llm = self._get_llm(1)
            browser_profile = self._make_browser_profile()
            browser = Browser(browser_profile=browser_profile)
            self._browser = browser

            agent = Agent(
                task=task_prompt,
                llm=llm,
                browser=browser,
                max_actions_per_step=2,
                use_vision=True,
                demo_mode=True,
                register_new_step_callback=self._on_step,
                register_should_stop_callback=self._should_stop,
            )

            history = await agent.run(max_steps=20)

            self._record_thought(
                'Gmail check completed',
                'Processing results',
                str(history.final_result())[:500] if history else '',
            )
            return {'status': 'checked', 'result': str(history.final_result())[:2000] if history else ''}

        except Exception as exc:
            self._record_thought('Gmail check failed', str(exc))
            return {'status': 'error', 'error': str(exc)}
        finally:
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

    # -- Prompt builders -----------------------------------------------------

    def _build_search_task(
        self,
        profile: CandidateProfile,
        preferences: SearchPreferences,
        search_url: str,
    ) -> str:
        roles_str = ', '.join(preferences.roles[:5])
        keywords_str = ', '.join(preferences.keywords[:8])
        locations_str = ', '.join(preferences.locations[:6])

        resume_path = profile.resume_file()
        resume_instruction = ''
        if resume_path and resume_path.exists():
            resume_instruction = f'\n- When a file upload for CV/Resume is required, upload this file: {resume_path.resolve()}'

        return f"""
You are an AI job application assistant helping {profile.full_name} find and apply to jobs.

## YOUR TASK
1. Go to {search_url}
2. If there are cookie banners, privacy popups, or consent dialogs — ACCEPT/DISMISS them first.
3. Search for jobs matching these criteria:
   - Roles: {roles_str}
   - Keywords: {keywords_str}
   - Locations: {locations_str}
   - Employment types: {', '.join(preferences.employment_types)}
4. Browse through the job listings. For each relevant job that matches the criteria:
   a. Click on it to open the full job description
   b. Look for an "Apply" or "Bewerben" button
   c. Fill out the application form with these details:
      - First name: {profile.first_name}
      - Last name: {profile.last_name}
      - Email: {profile.email}
      - Phone: {profile.phone}
      - City: {profile.city}
      - Country: {profile.country}
      - University: {profile.university}
      - Degree: {profile.degree_program}
      - LinkedIn: {profile.linkedin_url}
      - GitHub: {profile.github_url}
      - Available from: {profile.available_from}
      - Skills: {', '.join(profile.skills)}
      - Languages: {', '.join(profile.languages)}
      - Work authorization in Germany: {'Yes' if profile.authorized_to_work_in_germany else 'No'}
      - Visa sponsorship needed: {'Yes' if profile.need_visa_sponsorship else 'No'}{resume_instruction}
   d. For cover letter or motivation fields, write a brief professional cover letter mentioning:
      - Student at {profile.university} studying {profile.degree_program}
      - Practical experience building AI agentic systems
      - Enthusiasm for the specific company and role
      - Availability: {profile.available_from}
   e. Check any privacy/consent checkboxes
   f. DO NOT submit the application yet — stop before the final submit button so the user can review

5. After processing jobs, go back to the listings and continue with the next job.

## IMPORTANT RULES
- Always handle cookie banners and popups first
- Skip jobs that require senior experience or many years of professional work
- Focus on internships (Praktikum) and working student (Werkstudent) positions
- If a page fails to load or shows an error, skip it and move to the next job
- Be patient — wait for pages to fully load before interacting
- If you encounter a CAPTCHA, stop and note it in your response
"""

    def _build_apply_task(
        self,
        profile: CandidateProfile,
        job_url: str,
        company: str,
        job_title: str,
    ) -> str:
        resume_path = profile.resume_file()
        resume_instruction = ''
        if resume_path and resume_path.exists():
            resume_instruction = f'\n- When a file upload for CV/Resume is required, upload: {resume_path.resolve()}'

        return f"""
You are applying to: {job_title} at {company}
Job URL: {job_url}

## STEPS
1. Go to {job_url}
2. Handle any cookie banners or popups
3. Find and click the "Apply" / "Bewerben" / "Apply Now" button
4. Fill out the application form with:
   - First name: {profile.first_name}
   - Last name: {profile.last_name}
   - Email: {profile.email}
   - Phone: {profile.phone}
   - City: {profile.city}, {profile.country}
   - University: {profile.university}
   - Degree: {profile.degree_program}
   - LinkedIn: {profile.linkedin_url}{resume_instruction}
5. For any cover letter or motivation text, write a brief professional message about being a {profile.degree_program} student at {profile.university} excited about this role at {company}.
6. Check any privacy/terms checkboxes
7. Stop before final submission so the user can review

If you encounter errors or CAPTCHAs, report them.
"""
