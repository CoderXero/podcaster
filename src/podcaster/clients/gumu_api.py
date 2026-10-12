from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GumuAPIError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class GumuAPI:
    def __init__(self, base_url: str, token_provider: Any, timeout: float = 60):
        if not base_url:
            raise GumuAPIError("publishing api_base_url is not configured")
        self.base_url, self.token_provider, self.timeout = base_url.rstrip("/"), token_provider, timeout

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.token_provider.token()}", "Content-Type": "application/json"}
        request = Request(self.base_url + path, data=data, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            raise GumuAPIError(f"Gumu-Gumu API HTTP error {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise GumuAPIError(f"Gumu-Gumu API network failure (outcome uncertain): {error}", uncertain=True) from error

    def create_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/api/v1/episodes", payload)

    def publish(self, remote_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/episodes/{remote_id}/publish")

    def get_episode(self, remote_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/episodes/{remote_id}")
