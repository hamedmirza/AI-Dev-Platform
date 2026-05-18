
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


def _lmstudio_response_detail(response: httpx.Response) -> str:
    """Best-effort extract LM Studio / OpenAI-style error text for operators."""
    try:
        data = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return text[:800] if text else "(empty body)"
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str):
            return err
        msg = data.get("message")
        if msg:
            return str(msg)
    return str(data)[:800]


_DEFAULT_JSON_SCHEMA = {
    "name": "agent_response",
    "strict": False,
    "schema": {"type": "object", "additionalProperties": True},
}


class LMStudioProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(
            timeout=self.settings.provider_timeout_seconds,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"Connection": "keep-alive"},
        )
        # Cached negotiated response_format. None means "still unknown / try json_schema first";
        # once a 400 happens for a given format we downgrade and remember so we stop spamming
        # the server (and the logs) with rejected requests.
        self._response_format_mode: Optional[str] = None  # "json_schema" | "text" | "none"

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
        return LMStudioProvider(
            self.settings.model_copy(update={"lmstudio_model": model_name})
        )

    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        return self.structured_completion(system_prompt, user_prompt)

    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        return self.structured_completion(system_prompt, user_prompt)

    def _build_messages(
        self, system_prompt: str, user_prompt: str, *, with_json_nudge: bool
    ) -> list[dict[str, str]]:
        if with_json_nudge:
            user_content = (
                f"{user_prompt}\n\nReturn valid JSON only. Do not include markdown fences."
            )
        else:
            user_content = user_prompt
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _build_payload(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        """Construct request payload using the currently negotiated response_format.

        Order of preference (set once per provider instance via 400 feedback):
        1. ``json_schema`` — LM Studio's native structured format.
        2. ``text`` — explicit plain-text format with a JSON nudge in the user prompt.
        3. ``none`` — no ``response_format`` field at all.
        """
        mode = self._response_format_mode or "json_schema"
        if mode == "json_schema":
            return {
                "model": model,
                "response_format": {"type": "json_schema", "json_schema": _DEFAULT_JSON_SCHEMA},
                "messages": self._build_messages(
                    system_prompt, user_prompt, with_json_nudge=False
                ),
            }
        if mode == "text":
            return {
                "model": model,
                "response_format": {"type": "text"},
                "messages": self._build_messages(
                    system_prompt, user_prompt, with_json_nudge=True
                ),
            }
        return {
            "model": model,
            "messages": self._build_messages(system_prompt, user_prompt, with_json_nudge=True),
        }

    def structured_completion(self, system_prompt: str, user_prompt: str) -> str:
        model = (self.settings.lmstudio_model or "").strip()
        if not model:
            raise ProviderError("LM Studio model is not configured (LMSTUDIO_MODEL is empty).")

        url = f"{self.settings.lmstudio_base_url.rstrip('/')}/chat/completions"
        started = time.perf_counter()
        try:
            payload = self._build_payload(model, system_prompt, user_prompt)
            response = self._client.post(url, headers=self._headers(), json=payload)
            # Downgrade response_format on 400 (once per provider lifetime), then retry.
            if response.status_code == 400 and self._response_format_mode != "none":
                detail = _lmstudio_response_detail(response)
                previous_mode = self._response_format_mode or "json_schema"
                next_mode = "text" if previous_mode == "json_schema" else "none"
                logger.warning(
                    "lmstudio response_format=%s rejected (400) detail=%s; "
                    "downgrading to response_format=%s for this provider lifetime model=%s",
                    previous_mode,
                    detail,
                    next_mode,
                    model,
                )
                self._response_format_mode = next_mode
                payload = self._build_payload(model, system_prompt, user_prompt)
                response = self._client.post(url, headers=self._headers(), json=payload)
                if response.status_code == 400 and self._response_format_mode == "text":
                    # Server rejects "text" too — final downgrade to no response_format at all.
                    detail = _lmstudio_response_detail(response)
                    logger.warning(
                        "lmstudio response_format=text rejected (400) detail=%s; "
                        "dropping response_format entirely model=%s",
                        detail,
                        model,
                    )
                    self._response_format_mode = "none"
                    payload = self._build_payload(model, system_prompt, user_prompt)
                    response = self._client.post(url, headers=self._headers(), json=payload)
            # If the *first* call returned 200 with json_schema, lock it in so subsequent
            # callers don't re-test the same negotiation.
            elif response.status_code == 200 and self._response_format_mode is None:
                self._response_format_mode = "json_schema"
            if response.is_client_error or response.is_server_error:
                detail = _lmstudio_response_detail(response)
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "lmstudio chat/completions error status=%s latency_ms=%.2f model=%s detail=%s",
                    response.status_code,
                    elapsed_ms,
                    model,
                    detail,
                )
                raise ProviderError(
                    f"LM Studio request failed: {response.status_code} "
                    f"{response.reason_phrase} — {detail}"
                )
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
            model,
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
            response = self._client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("lmstudio health_check ok latency_ms=%.2f", elapsed_ms)
            available = {item.get("id") for item in data.get("data", []) if isinstance(item, dict)}
            configured = (self.settings.lmstudio_model or "").strip()
            if configured in available:
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
            response = self._client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
            return sorted(
                [str(item.get("id")) for item in data.get("data", []) if isinstance(item, dict)]
            )
        except httpx.HTTPError:
            return []
