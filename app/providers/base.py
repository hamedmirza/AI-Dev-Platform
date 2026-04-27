
from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.provider import ProviderHealthResponse


class BaseProvider(ABC):
    # Legacy method kept for compatibility with existing test doubles/callers.
    @abstractmethod
    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    # Legacy method kept for compatibility with existing test doubles/callers.
    @abstractmethod
    def healthcheck(self) -> ProviderHealthResponse:
        raise NotImplementedError

    # Spec-aligned interface methods.
    def chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        return self.invoke_json(system_prompt, user_prompt)

    def structured_completion(self, system_prompt: str, user_prompt: str) -> str:
        return self.invoke_json(system_prompt, user_prompt)

    def health_check(self) -> ProviderHealthResponse:
        return self.healthcheck()

    def list_models(self) -> list[str]:
        return []

    def with_overrides(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> "BaseProvider":
        return self
