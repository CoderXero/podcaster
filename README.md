# Podcaster

Podcaster is a resumable, file-based Markdown-to-podcast pipeline. It creates a validated two-host script with Ollama, synthesizes approved turns with ElevenLabs, renders a checked MP3 with FFmpeg, and publishes only through explicitly configured remote storage and API contracts.

## Quick start

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp config.example.yaml ~/.config/podcaster/config.yaml
podcaster --help
podcaster doctor
podcaster scripter --input ~/Downloads/articles
podcaster script approve my-article
podcaster audio-maker --slug my-article
podcaster publisher --slug my-article --confirm-publish
```

`ELEVENLABS_API_KEY`, `PODCAST_CLIENT_ID`, and `PODCAST_CLIENT_SECRET` are read from the environment. Never put secrets in YAML, manifests, or logs. The default source disposition is archive. Permanent deletion requires both `--on-success delete` and `--confirm-delete`.

The standard test suite never calls Ollama, ElevenLabs, Azure, or the publishing API. Live paid/publication checks are intentionally opt-in and publisher preflight fails closed until the upload and API contract are validated.

## File contract

Scripts are paired `scripts/<slug>.json` and `scripts/<slug>.md`. JSON is the TTS source of truth. Editing Markdown without `podcaster script import <slug>` blocks audio generation. Packages contain `podcast.mp3`, `title`, `description.txt`, `show notes.txt`, `episode.json`, and a working manifest.

See [operations.md](docs/operations.md) for recovery and [api-contract.md](docs/api-contract.md) for the integration questions that must be answered before publication.
