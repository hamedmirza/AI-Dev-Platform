
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.providers.base import BaseProvider

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class BaseAgent:
    def __init__(self, provider: BaseProvider, prompt_path: str) -> None:
        self.provider = provider
        self.prompt_path = Path(prompt_path)

    def load_system_prompt(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8").strip()

    def run(self, user_prompt: str, schema: type[SchemaT]) -> SchemaT:
        raw = self.provider.invoke_json(self.load_system_prompt(), user_prompt)
        payload = json.loads(raw)
        return schema.model_validate(payload)
