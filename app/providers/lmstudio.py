
import logging
import time
from typing import Optional

import httpx

from app.core.enums import ProviderStatus
from app.core.exceptions import ProviderError
from app.core.settings import Settings
from app.providers.base import BaseProvider
from app.schemas.provider import ProviderHealthResponse

logger = logging.getLogger(__name__)


class LMStudioProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.lmstudio_api_key}"}

    def with_overrides(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> BaseProvider:
        if provider_name and provider_name != "lmstudio":
            raise ProviderError(f"Unsupported provider override: {provider_name}")
        if not model_name:
            return self
        return LMStudioProvider(self.settings.model_copy(update={"lmstudio_model": model_name}))

    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        return self.structured_completion(system_prompt, user_prompt)

    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        return self.structured_completion(system_prompt, user_prompt)

    def structured_completion(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/chat/completions"
        payload_with_json = {
            "model": self.settings.lmstudio_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        payload_fallback = {
            "model": self.settings.lmstudio_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{user_prompt}\n\nReturn valid JSON only. "
                        "Do not include markdown fences."
                    ),
                },
            ],
        }
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=self.settings.provider_timeout_seconds) as client:
                response = client.post(url, headers=self._headers(), json=payload_with_json)
                if response.status_code == 400:
                    logger.warning(
                        "lmstudio response_format rejected; "
                        "retrying without response_format model=%s",
                        self.settings.lmstudio_model,
                    )
                    response = client.post(url, headers=self._headers(), json=payload_fallback)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "lmstudio structured_completion failed latency_ms=%.2f error=%s",
                elapsed_ms,
                exc,
            )
            raise ProviderError(f"LM Studio request failed: {exc}") from exc

        data = response.json()
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "lmstudio structured_completion ok latency_ms=%.2f model=%s",
            elapsed_ms,
            self.settings.lmstudio_model,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "LM Studio response did not contain a valid message payload",
            ) from exc

    def healthcheck(self) -> ProviderHealthResponse:
        return self.health_check()

    def health_check(self) -> ProviderHealthResponse:
        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/models"
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=min(self.settings.provider_timeout_seconds, 10.0)) as client:
                response = client.get(url, headers=self._headers())
                response.raise_for_status()
            data = response.json()
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("lmstudio health_check ok latency_ms=%.2f", elapsed_ms)
            available = {item.get("id") for item in data.get("data", []) if isinstance(item, dict)}
            if self.settings.lmstudio_model in available:
                return ProviderHealthResponse(
                    provider="lmstudio",
                    status=ProviderStatus.HEALTHY,
                    detail="LM Studio reachable and configured model is listed.",
                    model=self.settings.lmstudio_model,
                )
            return ProviderHealthResponse(
                provider="lmstudio",
                status=ProviderStatus.DEGRADED,
                detail="LM Studio reachable, but configured model was not listed.",
                model=self.settings.lmstudio_model,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.warning("lmstudio health_check failed latency_ms=%.2f error=%s", elapsed_ms, exc)
            return ProviderHealthResponse(
                provider="lmstudio",
                status=ProviderStatus.UNAVAILABLE,
                detail=f"LM Studio healthcheck failed: {exc}",
                model=self.settings.lmstudio_model,
            )

    def list_models(self) -> list[str]:
        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/models"
        try:
            with httpx.Client(timeout=min(self.settings.provider_timeout_seconds, 10.0)) as client:
                response = client.get(url, headers=self._headers())
                response.raise_for_status()
            data = response.json()
            return sorted(
                [str(item.get("id")) for item in data.get("data", []) if isinstance(item, dict)]
            )
        except httpx.HTTPError:
            return []
