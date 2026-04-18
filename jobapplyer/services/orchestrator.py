from __future__ import annotations

import asyncio
from typing import Any

from jobapplyer.browser.agent import BrowserAgent, AgentThought
from jobapplyer.config import AppSettings
from jobapplyer.db import Database
from jobapplyer.models import AgentSnapshot
from jobapplyer.profile import load_candidate_profile, load_search_preferences
from jobapplyer.utils import slugify, utcnow_iso


class JobApplyerOrchestrator:
    def __init__(self, settings: AppSettings, db: Database):
        self.settings = settings
        self.db = db
        self.snapshot_state = AgentSnapshot()
        self.agent = BrowserAgent(settings)
        self.agent.set_thought_callback(self._on_agent_thought)
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def _on_agent_thought(self, thought: AgentThought) -> None:
        """Called every time the AI agent has a new thought or takes an action."""
        self.snapshot_state.current_stage = thought.action or thought.thought
        self.db.record_event(
            event_id=slugify(f'thought-{thought.step}-{utcnow_iso()}'),
            event_type='agent_thought',
            message=f'Step {thought.step}: {thought.thought}',
            metadata={'action': thought.action, 'result': thought.result[:300] if thought.result else ''},
        )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self.snapshot_state.running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self.snapshot_state.running = False
        # Signal the browser-use agent to stop at the next step boundary
        self.agent.request_stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def shutdown(self) -> None:
        await self.stop()

    async def run_once(self) -> dict[str, Any]:
        async with self._lock:
            return await self._run_cycle()

    async def _loop(self) -> None:
        while self.snapshot_state.running:
            try:
                async with self._lock:
                    await self._run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.db.record_event(
                    event_id=slugify(f'cycle-error-{utcnow_iso()}'),
                    event_type='cycle_error',
                    message=str(exc),
                    metadata={'stage': self.snapshot_state.current_stage},
                )
                self.snapshot_state.last_cycle_summary = f'Cycle error: {exc}'
            await asyncio.sleep(self.settings.run_interval_seconds)

    async def _run_cycle(self) -> dict[str, Any]:
        self.snapshot_state.current_stage = 'starting'
        self.snapshot_state.last_cycle_at = utcnow_iso()

        profile = load_candidate_profile(self.settings)
        preferences = load_search_preferences(self.settings)

        # --- Phase 1: Search & Apply using AI Agent ---
        self.snapshot_state.current_stage = 'searching & applying (AI agent)'
        self.db.record_event(
            event_id=slugify(f'cycle-start-{utcnow_iso()}'),
            event_type='cycle_start',
            message=f'Starting AI agent cycle on {self.settings.job_tab_start_url}',
        )

        search_result = await self.agent.search_and_apply(
            profile=profile,
            preferences=preferences,
            search_url=self.settings.job_tab_start_url,
        )

        # --- Phase 2: Check Gmail for responses ---
        self.snapshot_state.current_stage = 'checking email'
        gmail_result: dict[str, Any] = {}
        try:
            gmail_result = await self.agent.check_gmail(self.settings.gmail_url)
        except Exception as exc:
            gmail_result = {'status': 'error', 'error': str(exc)}

        # --- Build summary ---
        summary = {
            'search_result': search_result,
            'gmail_result': gmail_result,
            'agent_steps': len(self.agent.thoughts),
        }

        self.snapshot_state.current_stage = 'idle'
        self.snapshot_state.current_company = ''
        self.snapshot_state.current_job = ''
        self.snapshot_state.last_cycle_summary = (
            f"AI agent completed {len(self.agent.thoughts)} steps. "
            f"Errors: {len(search_result.get('errors', []))}"
        )

        self.db.record_event(
            event_id=slugify(f'cycle-done-{utcnow_iso()}'),
            event_type='cycle_complete',
            message=self.snapshot_state.last_cycle_summary,
            metadata=summary,
        )

        return summary

    def snapshot(self) -> dict[str, Any]:
        return self.snapshot_state.model_dump()

    def get_agent_thoughts(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.agent.get_recent_thoughts(limit)
