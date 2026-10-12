from pathlib import Path

from podcaster.config import Config, PathsConfig, ScripterConfig
from podcaster.scripter import process_article


def test_failed_generation_retains_original(tmp_path: Path, monkeypatch):
    article = tmp_path / "article.md"
    article.write_text("# Article\n\nImportant content remains here.", encoding="utf-8")
    paths = PathsConfig(
        scripts=tmp_path / "scripts", podcasts=tmp_path / "podcasts", working=tmp_path / "working",
        archived_sources=tmp_path / "archive", completed_scripts=tmp_path / "completed", published=tmp_path / "published", logs=tmp_path / "logs",
    )
    config = Config(paths=paths, scripter=ScripterConfig(require_review=True))

    class Broken:
        def __init__(self, *args, **kwargs): pass
        def chat_json(self, *args, **kwargs): raise RuntimeError("offline")

    monkeypatch.setattr("podcaster.scripter.OllamaClient", Broken)
    try:
        process_article(article, config)
    except RuntimeError:
        pass
    assert article.exists()
    assert not (paths.scripts / "article.json").exists()
