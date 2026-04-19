
import httpx

from app.core.enums import ProviderStatus
from app.core.exceptions import ProviderError
from app.core.settings import Settings
from app.providers.base import BaseProvider
from app.schemas.provider import ProviderHealthResponse


class LMStudioProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.lmstudio_api_key}"}

    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.settings.lmstudio_model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            with httpx.Client(timeout=self.settings.provider_timeout_seconds) as client:
                response = client.post(url, headers=self._headers(), json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"LM Studio request failed: {exc}") from exc

        data = response.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "LM Studio response did not contain a valid message payload",
            ) from exc

    def healthcheck(self) -> ProviderHealthResponse:
        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/models"
        try:
            with httpx.Client(timeout=min(self.settings.provider_timeout_seconds, 10.0)) as client:
                response = client.get(url, headers=self._headers())
                response.raise_for_status()
            data = response.json()
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
            return ProviderHealthResponse(
                provider="lmstudio",
                status=ProviderStatus.UNAVAILABLE,
                detail=f"LM Studio healthcheck failed: {exc}",
                model=self.settings.lmstudio_model,
            )
