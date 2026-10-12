from pathlib import Path

import pytest

from podcaster.models import Manifest
from podcaster.observability import audit
from podcaster.state import transition


def test_state_transitions_are_persisted(tmp_path: Path):
    path = tmp_path / "manifest.json"
    manifest = Manifest(job_id="job", slug="job", stage="SOURCE_DISCOVERED")
    transition(manifest, "SCRIPT_GENERATING", path)
    assert '"stage": "SCRIPT_GENERATING"' in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        transition(manifest, "ARCHIVED", path)


def test_audit_redacts_credentials(tmp_path: Path):
    audit(tmp_path, "episode", "FAILED", error="Bearer supersecret https://blob.test/x?sig=private")
    content = (tmp_path / "episode.jsonl").read_text(encoding="utf-8")
    assert "supersecret" not in content
    assert "private" not in content
