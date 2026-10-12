from __future__ import annotations

import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse


class AzureBlobUploader:
    """Azure adapter returning private HTTPS blob URLs.

    The Gumu-Gumu backend must be granted access to these URLs by the deployment
    contract; this adapter deliberately does not make blobs public or create SAS
    URLs automatically.
    """

    def __init__(self, account_url: str, audio_container: str, image_container: str):
        if not account_url.startswith("https://") or not audio_container:
            raise ValueError("Azure HTTPS account URL and audio container are required")
        try:
            from azure.identity import DefaultAzureCredential
            from azure.storage.blob import BlobServiceClient, ContentSettings
        except ImportError as error:
            raise RuntimeError("install the optional azure extra to use Azure Blob storage") from error
        self.account_url = account_url.rstrip("/")
        self.audio_container, self.image_container = audio_container, image_container
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if connection_string:
            self.service = BlobServiceClient.from_connection_string(connection_string)
        else:
            self.service = BlobServiceClient(self.account_url, credential=DefaultAzureCredential())
        self._content_settings = ContentSettings

    def upload(self, local_path: Path, *, episode_key: str, mime_type: str) -> str:
        container = self.image_container if mime_type.startswith("image/") else self.audio_container
        if not container:
            raise ValueError("image container is not configured")
        suffix = ".jpg" if mime_type == "image/jpeg" else ".mp3"
        digest = hashlib.sha256(local_path.read_bytes()).hexdigest()[:16]
        blob_name = f"{episode_key}/{digest}{suffix}"
        client = self.service.get_blob_client(container=container, blob=blob_name)
        with local_path.open("rb") as stream:
            client.upload_blob(stream, overwrite=True, content_settings=self._content_settings(content_type=mime_type))
        return f"{self.account_url}/{container}/{blob_name}"

    def verify(self, uri: str, *, expected_sha256: str | None = None) -> bool:
        parsed = urlparse(uri)
        if parsed.scheme != "https" or not parsed.netloc:
            return False
        segments = parsed.path.lstrip("/").split("/", 1)
        if len(segments) != 2:
            return False
        blob = self.service.get_blob_client(container=segments[0], blob=segments[1])
        properties = blob.get_blob_properties()
        if expected_sha256 is None:
            return True
        digest = hashlib.sha256()
        for chunk in blob.download_blob().chunks():
            digest.update(chunk)
        return digest.hexdigest() == expected_sha256 and properties.size > 0
