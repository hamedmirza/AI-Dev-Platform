
from abc import ABC, abstractmethod

from app.schemas.provider import ProviderHealthResponse


class BaseProvider(ABC):
    @abstractmethod
    def invoke_json(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> ProviderHealthResponse:
        raise NotImplementedError
