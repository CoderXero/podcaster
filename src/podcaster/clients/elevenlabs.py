from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..filesystem import atomic_write_bytes


class ElevenLabsError(RuntimeError):
    pass


class ElevenLabsClient:
    def __init__(self, api_key: str, model: str, output_format: str, timeout: float = 180):
        if not api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")
        self.api_key, self.model, self.output_format, self.timeout = api_key, model, output_format, timeout

    def list_voices(self) -> list[str]:
        request = Request("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key": self.api_key})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            raise ElevenLabsError(f"could not list ElevenLabs voices: {error}") from error
        return [str(item["voice_id"]) for item in value.get("voices", []) if "voice_id" in item]

    def synthesize(self, text: str, voice_id: str, destination: Path) -> None:
        payload = {"text": text, "model_id": self.model, "output_format": self.output_format}
        request = Request(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "xi-api-key": self.api_key, "Accept": "audio/mpeg"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as error:
            if error.code in {401, 403, 402, 422}:
                raise ElevenLabsError(f"ElevenLabs request requires action ({error.code})") from error
            raise ElevenLabsError(f"ElevenLabs HTTP error {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise ElevenLabsError(f"ElevenLabs unavailable: {error}") from error
        if not data:
            raise ElevenLabsError("ElevenLabs returned an empty audio response")
        atomic_write_bytes(destination, data)

    def synthesize_dialogue(self, turns: list[tuple[str, str]], destination: Path) -> None:
        payload = {"inputs": [{"text": text, "voice_id": voice_id} for text, voice_id in turns], "model_id": self.model, "output_format": self.output_format}
        request = Request(
            "https://api.elevenlabs.io/v1/text-to-dialogue", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "xi-api-key": self.api_key, "Accept": "audio/mpeg"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as error:
            if error.code in {401, 403, 402, 422}:
                raise ElevenLabsError(f"ElevenLabs dialogue request requires action ({error.code})") from error
            raise ElevenLabsError(f"ElevenLabs dialogue HTTP error {error.code}") from error
        except (URLError, TimeoutError) as error:
            raise ElevenLabsError(f"ElevenLabs dialogue unavailable: {error}") from error
        if not data:
            raise ElevenLabsError("ElevenLabs returned an empty dialogue response")
        atomic_write_bytes(destination, data)
