from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from jobapplyer.config import AppSettings


class GeminiRateLimitError(RuntimeError):
    """Raised when Gemini returns a rate limit or quota response."""


class GeminiClientPool:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.keys = settings.gemini_api_keys
        self._cursor = 0
        self._client = httpx.AsyncClient(timeout=90.0)

    @property
    def enabled(self) -> bool:
        return bool(self.keys)

    async def close(self) -> None:
        await self._client.aclose()

    async def generate_text(
        self,
        prompt: str,
        model: str,
        *,
        system_instruction: str = '',
        temperature: float = 0.2,
        response_mime_type: str = 'text/plain',
    ) -> str:
        if not self.enabled:
            return ''
        payload = {
            'contents': [
                {
                    'role': 'user',
                    'parts': [{'text': prompt}],
                }
            ],
            'generationConfig': {
                'temperature': temperature,
                'responseMimeType': response_mime_type,
            },
        }
        if system_instruction:
            payload['systemInstruction'] = {'parts': [{'text': system_instruction}]}
        response = await self._request_with_rotation(model, payload)
        return self._extract_text(response)

    async def generate_json(
        self,
        prompt: str,
        model: str,
        *,
        system_instruction: str = '',
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        text = await self.generate_text(
            prompt,
            model,
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type='application/json',
        )
        if not text:
            return {}
        return self._parse_json(text)

    async def _request_with_rotation(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.keys:
            raise RuntimeError('No Gemini API keys configured.')

        last_error: Exception | None = None
        key_count = len(self.keys)

        for rotation_offset in range(key_count):
            key_index = (self._cursor + rotation_offset) % key_count
            key = self.keys[key_index]
            url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'

            for retry_number in range(self.settings.gemini_same_key_retries + 1):
                try:
                    response = await self._client.post(url, json=payload)
                    if response.status_code in {429, 503}:
                        raise GeminiRateLimitError(response.text)
                    response.raise_for_status()
                    data = response.json()
                    self._cursor = (key_index + 1) % key_count
                    return data
                except GeminiRateLimitError as exc:
                    last_error = exc
                    if retry_number < self.settings.gemini_same_key_retries:
                        await asyncio.sleep(self.settings.gemini_retry_backoff_seconds * (retry_number + 1))
                        continue
                    break
                except httpx.HTTPError as exc:
                    last_error = exc
                    break

        if last_error:
            raise last_error
        raise RuntimeError('Gemini request failed without a concrete error.')

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        candidates = payload.get('candidates') or []
        if not candidates:
            return ''
        parts = candidates[0].get('content', {}).get('parts', [])
        chunks = [part.get('text', '') for part in parts if isinstance(part, dict) and part.get('text')]
        return ''.join(chunks).strip()

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            return {}
        if text.startswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {'value': parsed}
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', text, re.S)
            if match:
                return json.loads(match.group(0))
            raise
