"""A minimal client for an OpenAI-compatible chat API (Groq by default).

Responses are cached on disk, keyed by a hash of the request, so re-running a
generation is free and reproducible. Tests pass a fake client and never touch
the network.

Configuration comes from the environment (or a local, git-ignored ``.env``):
``GROQ_API_KEY`` (or ``LLM_API_KEY``), and optionally ``LLM_MODEL`` and
``LLM_BASE_URL`` to point at another OpenAI-compatible provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


class InvalidJSONError(LLMError):
    """The model's reply was not a valid JSON object."""


class JSONChat(Protocol):
    model: str

    def complete_json(self, messages: list[dict], temperature: float = 0.0) -> dict: ...


def load_dotenv(path: str | Path = ".env") -> None:
    """Set variables from a ``KEY=value`` file without overriding the real environment."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass
class ChatClient:
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    base_url: str = field(default_factory=lambda: os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL))
    api_key: str | None = field(
        default_factory=lambda: os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY")
    )
    cache_dir: Path | None = Path(".cache/llm")
    timeout: float = 180.0
    max_retries: int = 5

    def complete_json(self, messages: list[dict], temperature: float = 0.0) -> dict:
        """Send a chat request that must answer with one JSON object, and parse it."""
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        cache_file = self._cache_file(body)
        if cache_file and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))["parsed"]

        response = self._post(body)
        text = response["choices"][0]["message"]["content"] or ""
        parsed = parse_json_object(text)
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "request": body,
                "content": text,
                "parsed": parsed,
                "usage": response.get("usage"),
            }
            cache_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return parsed

    def _cache_file(self, body: dict) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]
        return Path(self.cache_dir) / f"{digest}.json"

    def _post(self, body: dict) -> dict:
        if not self.api_key:
            raise LLMError("no API key: set GROQ_API_KEY in the environment or in .env")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "shadowcost/0.1",
            },
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as err:
                detail = err.read().decode(errors="replace")[:500]
                if "json_validate_failed" in detail:
                    raise InvalidJSONError(f"model did not return valid JSON: {detail}") from err
                if err.code not in _RETRY_STATUSES or attempt == self.max_retries:
                    raise LLMError(f"HTTP {err.code} from {self.base_url}: {detail}") from err
                wait = float(err.headers.get("retry-after") or 2**attempt)
            except (urllib.error.URLError, TimeoutError) as err:
                if attempt == self.max_retries:
                    raise LLMError(f"could not reach {self.base_url}: {err}") from err
                wait = 2**attempt
            time.sleep(min(wait, 60))
        raise LLMError("unreachable")


def parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating a surrounding ```json fence."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as err:
        raise InvalidJSONError(
            f"model did not return valid JSON: {err}; got {text[:200]!r}"
        ) from err
    if not isinstance(value, dict):
        raise InvalidJSONError("model returned JSON that is not an object")
    return value
