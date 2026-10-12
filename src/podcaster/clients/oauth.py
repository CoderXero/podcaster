from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class OAuthError(RuntimeError):
    pass


class ClientCredentialsToken:
    def __init__(self, discovery_url: str, client_id: str, client_secret: str, scope: str, timeout: float = 30):
        self.discovery_url, self.client_id, self.client_secret, self.scope, self.timeout = discovery_url, client_id, client_secret, scope, timeout
        self._token: str | None = None
        self._expires_at = 0.0

    def token(self) -> str:
        if self._token and time.time() < self._expires_at - 60:
            return self._token
        try:
            with urlopen(Request(self.discovery_url), timeout=self.timeout) as response:
                discovery = json.loads(response.read())
            endpoint = discovery.get("token_endpoint")
            if not endpoint:
                raise OAuthError("IdP discovery has no token_endpoint")
            body = urlencode({"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret, "scope": self.scope}).encode()
            with urlopen(Request(endpoint, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=self.timeout) as response:
                value = json.loads(response.read())
            self._token = value["access_token"]
            self._expires_at = time.time() + int(value.get("expires_in", 300))
            return self._token
        except (OSError, KeyError, ValueError) as error:
            raise OAuthError(f"could not obtain OAuth token: {error}") from error
