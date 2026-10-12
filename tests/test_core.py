from pathlib import Path

import pytest

from podcaster.config import PathsConfig
from podcaster.filesystem import discover_markdown, safe_slug
from podcaster.models import Host, Script, Segment
from podcaster.script_import_export import export_script, import_markdown, markdown_is_in_sync


def valid_script() -> Script:
    return Script(
        source_sha256="a" * 64,
        title="A Useful Episode",
        slug="a-useful-episode",
        summary="A summary",
        description="A description",
        show_notes="Sources: https://example.com/article",
        source_urls=["https://example.com/article"],
        speakers={"ALEX": Host(name="Alex Zulu", voice_id="alex"), "NAOMI": Host(name="Naomi Zed", voice_id="naomi")},
        segments=[
            Segment(index=0, speaker="ALEX", text="Welcome to this useful episode about a practical engineering topic."),
            Segment(index=1, speaker="NAOMI", text="We will explain the important details and the checks listeners should make."),
        ],
    )


def test_slug_and_discovery_skip_hidden_and_symlink(tmp_path: Path):
    assert safe_slug("A/B: C!") == "a-b-c"
    (tmp_path / "article.md").write_text("hello", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("hidden", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.md").write_text("ignored", encoding="utf-8")
    assert [path.name for path in discover_markdown(tmp_path)] == ["article.md"]


def test_markdown_round_trip_and_change_detection(tmp_path: Path):
    script = valid_script()
    script = export_script(script, tmp_path / "episode.md", tmp_path / "episode.json")
    assert markdown_is_in_sync(tmp_path / "episode.md", script)
    (tmp_path / "episode.md").write_text((tmp_path / "episode.md").read_text().replace("Welcome", "Greetings"), encoding="utf-8")
    assert not markdown_is_in_sync(tmp_path / "episode.md", script)
    imported = import_markdown(tmp_path / "episode.md", script)
    assert imported.script_revision == 2
    assert imported.script_status == "awaiting_review"


def test_script_rejects_noncontiguous_segments():
    with pytest.raises(ValueError):
        Script.model_validate(valid_script().model_dump() | {"segments": [Segment(index=1, speaker="ALEX", text="This has enough words to be valid as one turn.")]})


def test_paths_are_expanded():
    value = PathsConfig(scripts=Path("~/podcaster-tests"))
    assert not str(value.expanded().scripts).startswith("~")
