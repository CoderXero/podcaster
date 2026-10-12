from __future__ import annotations

import json
import random
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 240, retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retries = retries

    def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(f"{self.base_url}{endpoint}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except HTTPError as error:
                if error.code in {400, 404}:
                    raise OllamaError(f"Ollama request rejected ({error.code}); check model and configuration") from error
                if error.code not in {408, 429, 500, 502, 503, 504} or attempt >= self.retries:
                    raise OllamaError(f"Ollama HTTP error {error.code}") from error
            except (URLError, TimeoutError, ConnectionError) as error:
                if attempt >= self.retries:
                    raise OllamaError(f"Ollama unavailable: {error}") from error
            time.sleep(min(30, (2**attempt) + random.random()))
        raise OllamaError("Ollama request exhausted retries")

    def chat_json(self, system: str, user: str, *, num_ctx: int, temperature: float, max_output_tokens: int) -> dict[str, Any]:
        payload = {"model": self.model, "stream": False, "format": "json", "options": {
            "num_ctx": num_ctx, "temperature": temperature, "num_predict": max_output_tokens,
        }, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        result = self._request("/api/chat", payload)
        content = result.get("message", {}).get("content")
        if not isinstance(content, str):
            raise OllamaError("Ollama returned no message content")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as error:
            raise OllamaError("Ollama returned invalid JSON") from error
        if not isinstance(value, dict):
            raise OllamaError("Ollama JSON response must be an object")
        return value

    def doctor(self) -> dict[str, Any]:
        models = self._request("/api/tags", {})
        names = [item.get("name") for item in models.get("models", [])]
        if self.model not in names:
            raise OllamaError(f"configured model is not installed: {self.model}")
        self.chat_json("Return JSON only.", '{"ok": true}', num_ctx=1024, temperature=0, max_output_tokens=32)
        return {"reachable": True, "models": names, "model": self.model}
