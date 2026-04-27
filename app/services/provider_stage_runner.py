from __future__ import annotations

import json
import sys

from app.providers.registry import resolve_provider


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        provider_name = payload.get("provider_name")
        model_name = payload.get("model_name")
        system_prompt = payload["system_prompt"]
        user_prompt = payload["user_prompt"]
        provider = resolve_provider(provider_name, model_name)
        raw = provider.structured_completion(system_prompt, user_prompt)
        sys.stdout.write(json.dumps({"ok": True, "raw": raw}))
        return 0
    except Exception as exc:  # pragma: no cover - subprocess error surface
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
