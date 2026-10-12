# Podcaster — Production System Specification

**Version:** 1.0  
**Date:** 2026-10-11  
**Status:** Implementation-ready specification (external API integrations require contract validation)  
**Target:** Python 3.12+, Ubuntu/Linux first; portable to macOS/Windows  
**Podcast:** Gumu-Gumu (configurable)  
**Default hosts:** Alex Zulu ("X") and Naomi Zed ("Zee")

## 1. Objective

Build a reliable, resumable console pipeline that turns Markdown blog articles into natural two-person podcast conversations using a local or remote Ollama LLM, synthesizes the speakers using ElevenLabs, produces and validates a mastered MP3 and metadata, uploads media, creates and publishes an episode through the Gumu-Gumu REST API, and archives published episodes.

The system consists of **three separately runnable CLI commands** (`scripter`, `audio-maker`, `publisher`) and an optional coordinator (`podcaster`). Each stage can be invoked without the others and communicates via versioned, human-readable files. Each stage is safe to rerun, supports dry-run, creates audit logs and can resume after failure. **A failed step must never destroy the only copy of user content.**

### 1.1 Key corrections/assumptions

- The request to “remove the original article” is implemented as **archive by default**, with opt-in permanent deletion only after durable script generation and validation. Permanent removal cannot be undone; archive is strongly recommended.
- ElevenLabs **requires internet access** even when Ollama is local.
- The provided episode POST endpoint contains `audio_blob_uri` and `image_blob_uri`, so **an upload/storage mechanism is a required integration**. No upload endpoint, storage account, or supported URI scheme was supplied. Provide an abstraction and fail preflight until it is configured and tested. Never invent blob URIs or publish using `file://` paths.
- The episode creation API is treated as a draft creation operation as specified, but actual response schema, authentication requirements, URI accessibility requirements, and publication state must be discovered/confirmed against the target server.
- The generated `podcast.mp3` is a **final mix**, not a temporary track. Only temporary speech segments, scratch WAV files, and staging artifacts are deleted after validation.
- Existing source and output files are not overwritten without explicit `--force` and an auditable backup/versioning policy.

## 2. Architecture and data flow

```text
INPUT FOLDER (recursive *.md)
   │
   ▼
SCRIPTER  ── Ollama (localhost or remote)
   │          ├─ extract / structure article
   │          ├─ draft two-person dialogue
   │          ├─ verify facts / script / metadata
   │          └─ persist outputs atomically
   ▼
~/Downloads/output/scripts/<episode-slug>.md
~/Downloads/output/scripts/<episode-slug>.json
   │
   ▼
AUDIO MAKER ── ElevenLabs API (voice 1 / voice 2)
   │           ├─ generate/cache individual turns
   │           ├─ arrange intro → dialogue → outro
   │           ├─ normalize/mix/transcode using FFmpeg
   │           ├─ validate final audio
   │           └─ remove disposable temp tracks
   ▼
~/Downloads/output/podcasts/<episode-slug>/
   ├── podcast.mp3
   ├── title
   ├── show notes.txt
   ├── description.txt
   ├── episode.json
   ├── manifest.json
   └── cover.jpg              [if available/required]
   │
   ▼
PUBLISHER ── Auth client → Storage uploader → Gumu-Gumu Episodes API
   │           ├─ upload final MP3 (+ artwork)
   │           ├─ POST /api/v1/episodes → draft ID
   │           ├─ POST /api/v1/episodes/{id}/publish
   │           ├─ verify published state
   │           └─ archive entire folder atomically
   ▼
~/Music/podcasts/published/<episode-slug>/
```

### 2.1 Code design

Monorepo containing independently installable CLI entry points with a reusable Python package. No queue/database is necessary for single-machine MVP. Track state in individual JSON manifests, and use a lock and atomic file replacement. Optional SQLite job index for multi-worker orchestration, searchable history, and recovery; SQLite is **not** the canonical location of episode metadata. A future PostgreSQL/Redis worker backend may be added without changing files or CLI contracts.

- `scripter`: discovers source files, extracts article content, calls Ollama, validates output, writes Markdown script + canonical JSON, archives/removes processed source.
- `audio-maker`: parses structured turns (prefers `.json` paired with Markdown), synthesizes, orders, mixes, checks and packages audio.
- `publisher`: reads only ready packages, uploads media, creates/locates draft, publishes, verifies, moves package.
- `podcaster`: `run`, `status`, `doctor`, `retry`, `cleanup`, `review`, `validate` commands.
- `shared`: config, models, slugging, hashing, logging, Ollama/ElevenLabs/HTTP/storage/FFmpeg clients, filesystem locks and manifests.

## 3. Filesystem contract

All paths configurable; expand `~` with `Path.expanduser()`.

```text
~/Downloads/
├── articles/                         # example user-selected input
│   ├── microsoft-graph-changes.md
│   └── data-centre-plan.md
└── output/
    ├── scripts/
    │   ├── microsoft-graph-changes.md
    │   └── microsoft-graph-changes.json
    ├── podcasts/
    │   └── microsoft-graph-changes/
    │       ├── podcast.mp3
    │       ├── title
    │       ├── show notes.txt
    │       ├── description.txt
    │       ├── episode.json
    │       ├── manifest.json
    │       └── cover.jpg
    ├── working/                     # per-job temp, cache; ignored by publisher
    ├── archived-sources/            # safe default for original articles
    ├── completed-scripts/           # script archival after audio packaging
    ├── failed/                      # metadata/quarantine; originals retained
    └── logs/                        # structured JSONL logs
~/Music/podcasts/published/
    └── microsoft-graph-changes/
        ├── podcast.mp3
        ├── title
        ├── show notes.txt
        ├── description.txt
        ├── episode.json
        ├── manifest.json
        └── cover.jpg
```

- **Folder names:** lowercase ASCII-ish slug, hyphens, maximum 80 chars, suffix `-<8 char source sha256>` on collisions. Reject path traversal (`..`), absolute paths from metadata, symlink escapes and reserved filenames.
- **Idempotency key:** SHA-256 of normalized input article + versioned prompt/template + key script config. Audio identity additionally includes voice IDs, audio model, synthesis options and turn hashes. Publish identity is a stable UUID stored in `episode.json`, independent of local folder name.
- **Atomic writes:** write files in working dir then `fsync` and atomic rename/replace on same filesystem. For cross-filesystem moves, copy to destination staging folder, verify SHA-256, `fsync`, then finalize and remove source only after success.
- **Permissions:** credentials in env/secret store; chmod 0700 for work dirs and 0600 for sensitive local files where appropriate. Never log auth tokens or private article bodies by default.

## 4. Canonical schemas

### 4.1 Script Markdown (human review)

```markdown
---
schema_version: 1
source_id: "sha256:..."
episode_slug: "microsoft-graph-changes"
title: "Microsoft Graph Permission Changes Explained"
show: "Gumu-Gumu"
status: "script_ready"
topics: ["Microsoft Graph", "Security"]
tags: ["entra-id", "api-permissions"]
source_name: "microsoft-graph-changes.md"
---

# Microsoft Graph Permission Changes Explained

## Production notes
- Target length: 8–12 minutes.
- Alex Zulu (X): host; Naomi Zed (Zee): co-host.

## Script

**ALEX:** Welcome to Gumu-Gumu. Today we're unpacking a Microsoft Graph update.

**NAOMI:** And it has implications for applications using delegated permissions.

**ALEX:** Let's start with what is changing.

## Outro

**NAOMI:** Thanks for listening to Gumu-Gumu.
```

Markdown is a rendered/edited companion; the **versioned JSON** is the TTS source of truth, except when `podcaster script import` explicitly re-parses edited Markdown and regenerates the JSON. Editing Markdown alone must mark it out of sync and block `audio-maker` rather than silently synthesize stale content. Provide `script export`/`script import` and change detection.

### 4.2 Structured script JSON (`scripts/<slug>.json`)

```json
{
  "schema_version": 1,
  "episode_id": "c3537a92-15af-4759-91d0-12a1ac6d0640",
  "source_sha256": "...",
  "title": "Microsoft Graph Permission Changes Explained",
  "slug": "microsoft-graph-changes",
  "language": "en",
  "summary": "What developers should know about a Graph permission change.",
  "description": "Alex and Naomi explain an API permission update, its impact, and migration steps.",
  "show_notes": "Key points:\n- Changed permissions\n- Migration checks\n\nSources: ...",
  "topics": ["Security", "Microsoft Graph"],
  "tags": ["entra-id", "permissions"],
  "source_urls": ["https://example.com/article"],
  "speakers": {
    "ALEX": {"display_name": "Alex Zulu", "voice_ref": "host_1"},
    "NAOMI": {"display_name": "Naomi Zed", "voice_ref": "host_2"}
  },
  "segments": [
    {"index": 0, "speaker": "ALEX", "text": "Welcome to Gumu-Gumu.", "kind": "intro"},
    {"index": 1, "speaker": "NAOMI", "text": "Today we're discussing changes in Microsoft Graph.", "kind": "dialogue"}
  ],
  "script_status": "approved",
  "script_revision": 1,
  "prompt_version": "script-v1",
  "created_at": "2026-10-11T20:00:00Z"
}
```

Required JSON validations: non-empty title/summary/description/show_notes; 2 exactly configured speakers; non-empty ordered segments; one speaker per segment; index contiguous starting zero; no blank text, prompt artifacts or unsupported labels; reasonable duration/character budgets; tags/topics arrays of bounded non-empty strings; valid URL values if present. `episode_id` here is a local stable UUID, **not** the server-assigned episode ID.

### 4.3 Publishable package `episode.json`

```json
{
  "schema_version": 1,
  "local_episode_id": "c3537a92-15af-4759-91d0-12a1ac6d0640",
  "slug": "microsoft-graph-changes",
  "title": "Microsoft Graph Permission Changes Explained",
  "summary": "What developers should know about a Graph permission change.",
  "description": "Alex and Naomi explain ...",
  "show_notes": "Key points ...",
  "topics": ["Security", "Microsoft Graph"],
  "tags": ["entra-id", "permissions"],
  "audio_path": "podcast.mp3",
  "image_path": "cover.jpg",
  "audio_mime_type": "audio/mpeg",
  "duration_seconds": 520.4,
  "audio_sha256": "...",
  "ready_for_publish": true,
  "publish": {
    "state": "NOT_STARTED",
    "remote_episode_id": null,
    "audio_blob_uri": null,
    "image_blob_uri": null,
    "last_error": null,
    "published_at": null
  }
}
```

`manifest.json` tracks stage, detailed attempts, artifact hashes, provider request IDs, per-segment status, timestamps, prompt/model versions, retries, validation checks, review approval and errors. Persist each irreversible state transition before moving to the next step. Credentials must not be saved in manifest.

## 5. Scripter: precise behavior

### 5.1 CLI

```bash
podcaster scripter --input ~/Downloads/articles
podcaster scripter --input ~/Downloads/articles --recursive --dry-run
podcaster scripter --input ./blogs --ollama-url http://ivory:11434 --model gpt-oss:20b
podcaster scripter --input ./blogs --on-success archive
podcaster scripter --input ./blogs --on-success delete --confirm-delete
podcaster scripter --input ./blogs --review-required
podcaster scripter --input ./blogs --jobs 2 --continue-on-error
```

Aliases: standalone `scripter ...`. `--input` is required; `--recursive` defaults true; ignore hidden dirs, `.git`, output/archive paths and symlinks unless explicitly enabled; only `.md` / `.markdown` files by default. Honor `--include`, `--exclude`, `--max-files`, and `--max-input-bytes`.

### 5.2 Workflow

1. Validate input folder and prevent output being scanned as input. Discover Markdown files, sort deterministically, lock a given article.
2. Read UTF-8 (`utf-8-sig` accepted). Parse YAML frontmatter if present (title, author, source URL, date, tags). Remove HTML/script/comment boilerplate; preserve factual content, code, tables and attribution.
3. Compute source hash and check existing completed manifest; identical files skip unless `--force`.
4. If too long for model context, break by headings/paragraphs with overlap, extract structured facts and attributed citations per chunk, then combine. Context-size detection must use configured effective Ollama context, reserve generation tokens, and avoid silently truncating articles.
5. Use system/template prompts to produce the **JSON schema**, not unconstrained Markdown. Temperature configurable; request Ollama JSON/schema-constrained output where supported; validate with Pydantic; retry schema repair a bounded number of times.
6. LLM builds a lively, technically accurate conversation between Alex and Naomi: informal but professional; complementary viewpoints; clear opening, transitions, explanations, examples, caveats, practical takeaways and closing. **Do not invent news, quotes, statistics or sources**. Differentiate reported claims from commentary. Keep voice scripts free of Markdown formatting, speaker-name prefixes inside text, long URLs and raw citation markup. Convert acronyms/technical terms to speakable form as needed while retaining accuracy.
7. Use explicit target duration and speech-rate assumptions (default 140–160 spoken words/minute combined), enforce configurable min/max duration and turn length. Split run-on turns; avoid monotonous alternation and filler.
8. Validate content facts against supplied article using a separate local LLM review pass plus deterministic checks. Flag uncertain facts for manual review rather than asserting correctness. Avoid treating potentially malicious article text as instructions; article is untrusted data.
9. Generate summary, description, show notes with links to real source URLs, topics, and tags. No fabricated external sources. Write JSON and Markdown to `scripts/` atomically, update manifest and require approval where configured.
10. **Only after script files are durably written and re-read successfully**, apply source disposition: `archive` (default), `keep`, or `delete` (requires `--confirm-delete`). Preserve relative subdirectory structure in archive and metadata in manifest. Archive collision-safe. On any validation or write error, source stays untouched; mark FAILED.

### 5.3 Ollama API integration

- Configurable URL e.g. `http://127.0.0.1:11434`, `http://ivory:11434`, with explicit connect/read timeouts, model name, `num_ctx`, temperature, seed and max output. Use `POST /api/chat` and supply messages including a system prompt, article context and format specification; handle JSON output; optional streaming and progress logging. Use the installed Ollama API compatibility/capabilities; do not assume a particular model supports large contexts or JSON schema.
- `doctor`: verify host reachability, list of available models, configured model found, and tested minimal structured response. Never auto-pull multi-GB models without consent.
- Retry connection reset, 429 and transient 5xx with exponential backoff/jitter; fail fast on bad model ID, invalid configuration or unsupported capabilities. Local/remote traffic may contain proprietary article text; recommend TLS/tunnel/allowlisted LAN for remote instances.
- Prompt assets version-controlled: `prompts/script_system.j2`, `script_user.j2`, `facts_review.j2`, `metadata.j2`, `intro_outro.j2`.

### 5.4 Scripter acceptance

Given two valid articles, Scripter produces two different, valid, reviewable scripts and metadata. Running again without changes is a no-op. A failed Ollama call preserves originals. The `delete` option never runs until output checks pass and never deletes unrelated files.

## 6. Audio Maker: precise behavior

### 6.1 CLI

```bash
podcaster audio-maker
podcaster audio-maker --scripts ~/Downloads/output/scripts --jobs 1
podcaster audio-maker --slug microsoft-graph-changes --dry-run
podcaster audio-maker --slug microsoft-graph-changes --regenerate
podcaster audio-maker --slug microsoft-graph-changes --intro assets/intro.mp3 --outro assets/outro.mp3
podcaster audio-maker --slug microsoft-graph-changes --tts-mode turns
podcaster audio-maker --slug microsoft-graph-changes --tts-mode dialogue
```

Defaults to scanning `~/Downloads/output/scripts/*.json` with matching `.md` files; `.md`-only files are accepted **only** through explicit import/validation path, not by blindly passing Markdown (speaker labels may leak into speech). Standalone alias `audio-maker`.

### 6.2 Voices and ElevenLabs

Default voice names may be configured from the previously defined Gumu-Gumu hosts:

- `ALEX` / Alex Zulu (X): `orS9zubkf3wfUBO5E2mK`
- `NAOMI` / Naomi Zed (Zee): `g0IlXuNNtW9CjDtDGv70`

These are **configuration defaults**, not guarantees the ElevenLabs account can access them. `doctor` must check entitlement/voice availability and a short real synthesis only when `--test-paid-api` is explicitly passed. Do not auto-generate a paid test.

- Store `ELEVENLABS_API_KEY` in environment or OS keyring; use official Python SDK or `httpx`, `xi-api-key` header.
- Default mode **turns**: call `POST /v1/text-to-speech/{voice_id}` for each turn, passing text, compatible model ID, settings, and a consistent `output_format` such as `mp3_44100_128` (tier-dependent). Write responses directly to disk with atomic `.part` → finalized transition; never buffer full long recordings unnecessarily.
- Optional **dialogue**: `POST /v1/text-to-dialogue` using ordered `{text, voice_id}` inputs; choose a model supporting dialogue, group adjacent turns into coherent requests, and stay within the provider's recommended request size (documentation recommends total inputs text at or below ~2,000 characters for reliability). Trade-off: richer pacing but less per-turn editing/retry granularity.
- Each chunk has SHA-256 cache key of normalized text, voice ID, model/version, output format, voice settings and provider mode. Reuse only verified matching audio; partial or corrupted files are regenerated. Avoid duplicate charge on retry when a previously saved successful response exists. Provider errors that occur after synthesis but before client receives audio may still incur billing; report the risk.
- Strip stage directions unless deliberately mapped to a model-supported speech prompt. Preserve spoken punctuation, correct pronunciation of acronyms and numbers. Never include Markdown backticks or `**ALEX:**` in API text.
- Handle 401/403 invalid credentials/permissions as stop conditions, 402/credit exhaustion/plan limits as actionable pause, 429 with `Retry-After` and rate limiter, 408/5xx/network errors with bounded retries and jitter, 422 as bad request requiring repair (no blind retry). Concurrency default 1, configurable with per-account ceiling; estimate character consumption before starting.

Official reference: [Text to Speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Text to Dialogue](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert/), and [API Introduction](https://elevenlabs.io/docs/api-reference/introduction/). Check model compatibility and rate limits at implementation time.

### 6.3 Intro/outro and sequence

Production playlist determined by structured segment `index`, never filesystem glob order:

```text
[optional licensed intro music]
→ [optional spoken program intro, generated or pre-recorded]
→ dialogue segments ordered 0..N-1
→ [optional spoken outro, generated or pre-recorded]
→ [optional licensed outro music]
```

Avoid duplicate spoken intros/outros: script segment kinds `intro`/`outro` and externally generated openings must follow `intro_policy`: `script_only` (default), `external_only`, or `combine`. Music is optional; require appropriate rights/license and avoid abrupt cuts. Configurable fade in/out, 150–350 ms inter-turn silence (default 200 ms) and music ducking when mixed under speech.

### 6.4 Audio engineering

- Check `ffmpeg` and `ffprobe` installed, enforce source audio decoding, fail if an individual segment is zero bytes, truncated or unintelligible on decode.
- Convert all input tracks to same internal PCM representation (recommended 48 kHz stereo WAV for processing; channel decisions configurable), add silence gaps, then concatenate with FFmpeg filtergraph; avoid naive binary MP3 concatenation which can introduce discontinuities.
- Apply loudness normalization suitable for podcast distribution (configurable target, e.g. -16 LUFS stereo or -19 LUFS mono, true peak max -1.0 dBTP), optionally gentle dynamics processing; prevent clipping and excessive background music. Always inspect integrated LUFS/true peak on final render using loudnorm/ebur128 analysis.
- Export MP3 using libmp3lame at supported rate (default 44.1 kHz, stereo, 128–192 kbps); embed ID3 title, artist, album/podcast name, date, comment and cover art where available.
- Validate actual duration >0, expected approximate duration, decode to end, seek test, file size, codec and MIME. Do not mark READY if validations fail.
- Produce required exact filenames `podcast.mp3`, `title`, `show notes.txt`, `description.txt`; package also contains `episode.json`, `manifest.json`, optional `cover.jpg`. Content of `title` is a single UTF-8 line. `description.txt` is a concise episode description; `show notes.txt` has fuller timestamped outline where reliable, source attribution and links. Do not invent timestamps: derive from generated segment durations if included.
- If artwork required by publication API or podcast site, support `--image` or configured default artwork; **no automatic image generation assumed**. Missing required artwork should block publish at preflight.
- After output fully verified and atomic package completed, remove only matching job's `working/<job-id>/segments` and intermediate PCM. Preserve failed-work cache until retry or configured TTL; do not purge unrelated files. Default retain source scripts in `completed-scripts/` for reproducibility; optionally leave originals in `scripts/` marked consumed.

### 6.5 Audio acceptance

Test with five alternating turns. Output is one correctly ordered MP3 with stable level, correct voices, intro/outro included exactly once, and required metadata. Simulated rate limit resumes without re-synthesizing successful turns; final generation cleans only disposable files.

## 7. Publisher: precise behavior

### 7.1 CLI

```bash
podcaster publisher --dry-run
podcaster publisher --slug microsoft-graph-changes
podcaster publisher --all --confirm-publish
podcaster publisher --slug microsoft-graph-changes --resume
podcaster publisher --slug microsoft-graph-changes --upload-only
podcaster publisher --slug microsoft-graph-changes --create-draft-only
```

Standalone alias `publisher`. Scans `~/Downloads/output/podcasts/<slug>/` for `episode.json` with `ready_for_publish=true` and `publish.state != PUBLISHED`; never treats any arbitrary directory or file as publishable. Skip folders currently locked by audio stage. By default **draft + explicit publish require `--confirm-publish`**, or a configured `publishing.auto_publish=true` for unattended pipelines.

### 7.2 Preflight

1. Acquire exclusive per-episode lock; validate schema, files, SHA-256, MIME and audio duration.
2. Verify credentials to IdP/REST API, API base URL and HTTPS production requirement.
3. Verify valid upload destination exists and storage credentials can upload and read final content as required by API.
4. Confirm artwork requirement, summary/description/show-notes length limits, topics/tags vocabularies and any publication policy.
5. Check existing `remote_episode_id` or configurable lookup by client reference to avoid duplicates.
6. Write `PUBLISHING` state to local manifest; ensure retry strategy is safe across uncertain network outcomes.

### 7.3 Storage uploader (mandatory adapter)

The supplied API request accepts blob URIs. Define interface:

```python
class MediaUploader(Protocol):
    async def upload(self, local_path: Path, *, episode_key: str, mime_type: str) -> str: ...
    async def verify(self, uri: str, *, expected_sha256: str | None = None) -> bool: ...
```

Support adapters, selected by config:

- **Azure Blob Storage** (preferred for Azure-hosted Gumu-Gumu): upload `podcast.mp3` to a configured container and optional `cover.jpg` to image container; use `azure-storage-blob` and Azure Identity/managed identity when available, otherwise scoped credentials. Return URI format **accepted by Gumu-Gumu backend**. A private `https://...blob.core.windows.net/...` URI may work only if the backend itself can read it via managed identity; public read or SAS URIs must be agreed, secured and rotated with care. Never log SAS query strings.
- **Gumu-Gumu upload API**: only if the server actually exposes upload/presigned-upload endpoint; implementation waits for real contract.
- **Local/no-op**: useful for integration tests only; must not publish because remote API cannot read local files.

Prefer private blobs with backend identity access, randomized blob names or deterministic `local_episode_id` paths, content type `audio/mpeg`, and server-side encryption. Verify blob length/content hash or download/read range where permitted. Configure storage lifecycle separately, never delete source blob on ambiguous publish failure.

### 7.4 Episode creation contract

As provided:

```http
POST {api_base_url}/api/v1/episodes
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "title": "Microsoft Graph Permission Changes Explained",
  "summary": "What developers should know about a Graph permission change.",
  "description": "Alex and Naomi explain ...",
  "show_notes": "Key points ...",
  "topics": ["Security", "Microsoft Graph"],
  "tags": ["entra-id", "permissions"],
  "audio_blob_uri": "https://<configured-account>.blob.core.windows.net/<container>/<object>.mp3",
  "audio_mime_type": "audio/mpeg",
  "image_blob_uri": "https://<configured-account>.blob.core.windows.net/<container>/<object>.jpg"
}
```

Map `title` from `title`/`episode.json`, `summary` from `episode.json.summary` (not necessarily same as description), `description` from `description.txt`, `show_notes` from `show notes.txt`, topics/tags from `episode.json`; blob URIs must be returned by configured uploader. **If `image_blob_uri` is mandatory and no image exists, fail preflight**; if API supports null/omission, feature flag this only after contract validation.

- OAuth2 client credentials is recommended for unattended machine publishing **if the IdP and API support it**. IdP discovery URL: `https://iam.zambeziblue.com/.well-known/openid-configuration`. Load token endpoint, use configured client ID/secret, API audience/scope, cache token until shortly before expiry, do not hard-code secrets. If server uses delegated auth instead, support device authorization/authorization code + PKCE only after confirming supported grants.
- Treat response on successful creation as source for `remote_episode_id`, but **field name is unconfirmed** (`id`, `episode_id`, etc.). Define a configurable response selector or validate OpenAPI schema; reject missing ID rather than guessing. Persist remote ID and full sanitized response immediately before requesting publication.
- API timeouts after POST could mean a draft was actually created. Do **not** blindly repeat POST. Look up by stable client reference if an endpoint supports it, otherwise require operator reconciliation and resume using `--remote-episode-id` (validated). Send `Idempotency-Key` only if backend explicitly supports it. Recommend backend support for unique `external_reference=local_episode_id`/idempotency key.

### 7.5 Publish endpoint

```http
POST {api_base_url}/api/v1/episodes/{episode_id}/publish
Authorization: Bearer <access_token>
Content-Length: 0
```

No JSON request body. Handle 200/201/202/204 according to actual server contract (202 requires polling/verification). Persist `PUBLISH_REQUESTED`; **verify remote published state with `GET /api/v1/episodes/{id}` or configured official read endpoint before archive**. If no read endpoint exists, rely only on a contractually definitive synchronous publish response; otherwise mark `VERIFY_REQUIRED` and leave local package in place. A network timeout on publish must trigger state reconciliation, not a blind second POST.

### 7.6 Final archive

After verification set `PUBLISHED` and record remote ID, timestamps and blob URIs (without secret query strings). Move folder from `~/Downloads/output/podcasts/<slug>` to `~/Music/podcasts/published/<slug>` with collision strategy, verify checksums, and commit archive marker. Retain `podcast.mp3` and all metadata. Archive failures are `PUBLISHED_ARCHIVE_PENDING`, not failed publication; next `--resume` retries only archive, never republishes.

## 8. State machine, recovery and concurrency

```text
SOURCE_DISCOVERED → SCRIPT_GENERATING → SCRIPT_READY [→ AWAITING_APPROVAL]
    → SCRIPT_APPROVED → AUDIO_GENERATING → AUDIO_PACKAGING → AUDIO_READY
    → UPLOADING → UPLOADED → DRAFT_CREATING → DRAFT_CREATED
    → PUBLISH_REQUESTED → PUBLISHED_VERIFIED → ARCHIVING → ARCHIVED
```

On failure: record `failed_stage`, error type, attempts, timestamp and `last_good_state`. Retain verified artifacts. Resume from last safe checkpoint. **External POST operations have uncertain-outcome states** (`DRAFT_CREATE_UNKNOWN`, `PUBLISH_UNKNOWN`) requiring remote reconciliation before retry. There is no exactly-once guarantee without server-supported idempotency/lookup. Do not claim it.

Concurrency: per-article/episode file lock with PID/hostname/time and stale-lock recovery; Scripter parallelism default 1–2; ElevenLabs parallelism default 1; publisher default 1. Preserve sequence using explicit indices. Graceful SIGINT/SIGTERM stops scheduling, safely records progress, and leaves interrupted `.part` files uncommitted. Multi-host operation on shared folder is **not supported** in MVP without distributed coordination.

## 9. Configuration and secrets

Recommended `~/.config/podcaster/config.yaml` (no actual secrets):

```yaml
app:
  show_name: Gumu-Gumu
  language: en
  log_level: INFO
paths:
  scripts: ~/Downloads/output/scripts
  podcasts: ~/Downloads/output/podcasts
  working: ~/Downloads/output/working
  archived_sources: ~/Downloads/output/archived-sources
  completed_scripts: ~/Downloads/output/completed-scripts
  published: ~/Music/podcasts/published
  logs: ~/Downloads/output/logs
scripter:
  recursive: true
  source_disposition: archive   # keep | archive | delete
  require_review: true
  target_minutes: 10
  min_minutes: 5
  max_minutes: 15
  speech_words_per_minute: 150
  max_retries: 3
ollama:
  base_url: http://127.0.0.1:11434
  model: gpt-oss:20b
  num_ctx: 32768
  temperature: 0.5
  timeout_seconds: 240
hosts:
  ALEX:
    name: Alex Zulu
    voice_id: orS9zubkf3wfUBO5E2mK
  NAOMI:
    name: Naomi Zed
    voice_id: g0IlXuNNtW9CjDtDGv70
audio:
  tts_mode: turns
  elevenlabs_model: eleven_multilingual_v2  # confirm current support
  output_format: mp3_44100_128
  silence_ms_between_turns: 200
  intro_policy: script_only
  intro_music: null
  outro_music: null
  target_lufs: -16
  true_peak_db: -1.0
  mp3_bitrate: 160k
  retain_successful_segment_cache_days: 0
publishing:
  api_base_url: https://podcast.example.com
  idp_discovery_url: https://iam.zambeziblue.com/.well-known/openid-configuration
  oauth_scope: "<configured-api-scope>"
  auto_publish: false
  storage_adapter: azure_blob
  storage_account_url: https://<account>.blob.core.windows.net
  audio_container: podcast-audio
  image_container: podcast-images
  require_image: true
  create_response_id_field: id   # confirm against actual API
  publish_verification_enabled: true
  allow_http_localhost_only: true
```

`.env` example (do not commit):

```dotenv
ELEVENLABS_API_KEY=replace_me
PODCAST_CLIENT_ID=replace_me
PODCAST_CLIENT_SECRET=replace_me
# If using connection string instead of Azure Identity; never commit this:
# AZURE_STORAGE_CONNECTION_STRING=replace_me
```

Config precedence: CLI > environment > YAML > packaged defaults. Validate with Pydantic Settings; redact API keys, bearer tokens and SAS in errors/logs. Create `.env.example`, not `.env`, in repository. Prefer workload identity/managed identity or OS keychain over plaintext secrets. Set network timeouts and CA verification; never disable certificate checking in production.

## 10. CLI surface and user experience

```bash
podcaster --help
podcaster doctor [--test-paid-api]
podcaster scripter --input ~/Downloads/articles
podcaster script list
podcaster script show <slug>
podcaster script import <slug>      # after editing Markdown
podcaster script approve <slug>
podcaster audio-maker [--slug <slug>]
podcaster publisher --slug <slug> --confirm-publish
podcaster run --input ~/Downloads/articles --stop-after audio
podcaster run --input ~/Downloads/articles --confirm-publish
podcaster status [--json]
podcaster retry <slug> [--stage script|audio|publish]
podcaster validate <slug>
podcaster cleanup --older-than 7d --dry-run
```

`run`: coordinate the three stages in order, honor review-required pause and stop-after. Use Typer for CLI and Rich for user-visible progress/tables. Every operation supports `--dry-run` where meaningful. `--json` outputs structured status for automation. Exit codes: `0` all requested work complete, `1` one/more job failed, `2` configuration/usage error, `3` review/reconciliation required, `4` external dependency unavailable, `130` interrupted. Partial batch failure returns non-zero with per-item statuses.

Example console output:

```text
[1/2] microsoft-graph-changes  SCRIPT_READY → AUDIO_READY (00:09:41)
[2/2] data-centre-plan        AWAITING_APPROVAL
Publisher: 1 eligible, 0 published, 1 awaiting review
Run summary: succeeded=1 pending=1 failed=0
```

## 11. Dependencies and repository layout

```text
podcaster/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── .env.example
├── config.example.yaml
├── src/podcaster/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── state.py
│   ├── locks.py
│   ├── filesystem.py
│   ├── script_import_export.py
│   ├── scripter.py
│   ├── audio_maker.py
│   ├── publisher.py
│   ├── pipeline.py
│   ├── clients/
│   │   ├── ollama.py
│   │   ├── elevenlabs.py
│   │   ├── gumu_api.py
│   │   └── oauth.py
│   ├── storage/
│   │   ├── base.py
│   │   └── azure_blob.py
│   ├── audio/
│   │   ├── ffmpeg.py
│   │   ├── playlist.py
│   │   └── quality.py
│   └── prompts/
│       ├── script_system.j2
│       ├── script_user.j2
│       ├── facts_review.j2
│       └── metadata.j2
├── assets/intro.mp3               # optional user-provided file
├── assets/outro.mp3               # optional user-provided file
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    ├── api-contract.md
    ├── operations.md
    └── troubleshooting.md
```

Core dependencies: `typer`, `rich`, `pydantic`, `pydantic-settings`, `httpx`, `PyYAML`, `Jinja2`, `tenacity`, `filelock`, `python-dotenv` (development only), `azure-storage-blob`, `azure-identity`, `mutagen` (MP3/ID3), `python-slugify`; optional official `ollama` and `elevenlabs` Python clients. External: `ffmpeg`, `ffprobe`. Test: `pytest`, `pytest-asyncio`, `respx`, `ruff`, `mypy`, `coverage`. Pin compatible versions with a lockfile (`uv.lock`); avoid mixing redundant HTTP client layers unless justified.

Example installation on Ubuntu:

```bash
sudo apt update && sudo apt install -y ffmpeg
python3 --version                   # ensure >=3.12
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp config.example.yaml ~/.config/podcaster/config.yaml  # create parent first
podcaster doctor
```

Project may prefer `uv sync --extra dev` instead of pip/venv; document both supported paths.

## 12. API validation checklist (integration blockers)

Before publisher can go live, obtain/test:

1. Actual `api_base_url`, HTTPS certificate and network accessibility.
2. IdP supported client credentials grant, token endpoint, requested scope/audience, required roles/permissions, token validation expectations, 401/403 behavior.
3. Real `POST /api/v1/episodes` response body, draft status, returned ID field and error shape.
4. Whether any endpoint allows lookup by local external reference or supports an idempotency header.
5. `POST /api/v1/episodes/{id}/publish` success code, whether async and how to verify publication with GET.
6. Accepted `audio_blob_uri`/`image_blob_uri` URI scheme, blob visibility, backend storage access model, supported file sizes, mandatory image, file validation.
7. Field length/enum restrictions for title, summary, description, show_notes, topics and tags; whether edits to draft are supported.
8. Upload mechanism (Azure Blob account/container authorization or a real media-upload API), retention, CORS only if relevant.

Until these are confirmed, implement Publisher with mocked contract tests and **default to fail closed** in live mode.

## 13. Testing and release requirements

### 13.1 Unit testing

Input discovery/exclusion, slug collision, YAML frontmatter, text normalization, malformed UTF-8, source hashing, JSON schema, speaker order, Markdown round-trip, filesystem traversal, prompts, stage state transitions, archive vs delete guard, exact package filenames and metadata mapping.

### 13.2 Integration testing (mocked external APIs)

- Ollama: structured response, invalid JSON, context overflow, slow remote host, refusal/factual uncertainty and repair limit.
- ElevenLabs: 401, 403, exhausted credits, 429 Retry-After, timeout-after-success, corrupt MP3, resume/cache, long turns and dialogue chunk limit.
- FFmpeg: speech order, intro/outro once, loudness/peak, truncated output, unsupported codec, metadata tagging.
- Publisher: upload denied, missing image, URI inaccessible, draft created but response lost, duplicate request, token expiration, publish 202 pending, publish timeout/reconcile, archive cross-volume interruption.
- Concurrent invocation: lock contention and stale-lock recovery.

### 13.3 End-to-end acceptance scenarios

1. **Happy path:** markdown article → approved script → final MP3/required files → blob uploads → remote draft → publish → verified state → archived directory.
2. **Safe deletion:** script failure and output write failure always retain original; `--on-success delete` without explicit confirm is rejected.
3. **Idempotency:** rerun entire pipeline creates no duplicate speech, episodes or archives; identical input re-scan skips completed item.
4. **Resume:** kill process after third of eight turns; restart synthesizes only missing turns, then produces ordered output.
5. **No silent publish:** default needs explicit publish approval or configured unattended policy; failures are visible.
6. **Ambiguous remote create:** timeout after POST results in reconciliation state; no second draft until reconciled.
7. **Privacy:** logs and artifacts contain no ElevenLabs API keys, OAuth client secrets, bearer tokens or signed URLs.
8. **Audio QA:** final MP3 decodes, duration within reasonable limits, no missing turns, loudness within configured tolerance, no clipping.
9. **Review:** manually adjusted Markdown must be re-imported; generated JSON/audio reflects approved revisions.
10. **Batch:** one bad article does not cause other articles to disappear or become misidentified.

Quality gates: automated tests, Ruff, MyPy, dependency security audit, coverage goal ≥85% for core domain logic, shell CLI integration on Ubuntu, reproducible lockfile and tagged release. Use test account/sandbox for any calls that could incur ElevenLabs charges or publish publicly.

## 14. Security, policy and observability

- No embedded secrets, never print tokens, URLs with SAS signatures, request bodies containing proprietary articles or full TTS scripts to ordinary logs.
- Treat article content as **untrusted instruction-bearing input**; isolate from system prompt and validate citations and extracted facts. Do not execute article code/snippets or follow arbitrary URLs automatically.
- Prompt/script audit: record model and prompt version, input checksum, turn checksum, review outcome; do not present automated fact checking as perfect.
- Respect authorship/copyright: process content the operator is permitted to adapt; cite source in show notes; do not imply permission to republish third-party material.
- Ensure rights to voices/music and applicable ElevenLabs plan permissions; don't clone voices without authorization.
- Publishing needs explicit least-privilege credentials scoped to upload and episode management. Isolate test/prod environments with separate configs, identities and containers.
- Rate-limit and backoff per provider, meter generation length/character usage; emit job ID, stage, status, elapsed duration, model/voice IDs, total characters, external request IDs and sanitized error codes.
- Optional telemetry: JSONL logs, rotating log files and `podcaster status --json`; future OpenTelemetry exporters.

## 15. Delivery milestones

**M1 — Core CLI and schema:** project scaffold, config, domain models, file layouts, logs, locks, script importer/exporter, doctor, deterministic fixtures.

**M2 — Scripter:** local/remote Ollama, robust prompts, schema validation, fact-review stage, manual approval, source archive/delete safety, unit/integration tests.

**M3 — Audio Maker:** ElevenLabs turn mode, segment caching/retry, FFmpeg sequence/music/loudness, metadata packaging, quality verification; optional dialogue mode after base version works.

**M4 — Publisher:** OAuth2 client, Azure uploader, API contract validation, draft creation, publish/verify, safe archive, recovery from ambiguous HTTP outcomes.

**M5 — Coordinator and hardening:** full `run`, status/retry/review, E2E tests, operability, deployment docs, CI, release packaging.

### Definition of done

A fresh Ubuntu installation with Ollama and FFmpeg plus configured ElevenLabs, Azure storage and Gumu-Gumu credentials can process multiple Markdown articles and yield published, remotely accessible episodes while preserving a clear audit trail. Crashes, retries and partial network outages do not silently lose originals, duplicate publications or archive unverified episodes.

## 16. Implementation instructions for coding agent

1. Build this project as actual runnable Python 3 code, **not** only pseudocode. Use Python 3.12+, type hints, modular clients, strict Pydantic models and Typer commands.
2. Implement separate entry points for `scripter`, `audio-maker`, `publisher`, and consolidated `podcaster`. Share all business logic; do not copy it across binaries.
3. Keep external connectors behind interfaces; create contract tests and fake adapters before using paid/live APIs.
4. Implement full schema, state transitions, locks, incremental retry, atomic writes and safe file handling **before** source deletion or episode publishing.
5. Make all external endpoint/model/voice/auth values configurable. Use default voice IDs above but validate authorization.
6. Implement local/remote Ollama `doctor`, bounded retries, JSON-constrained generation and validation. Do not assume a model can sustain the configured context length.
7. Implement ElevenLabs turn synthesis and FFmpeg mastering; keep production order via segment indices; clean job-specific scratch only after integrity verification.
8. Do **not** implement fake Azure upload or assume a public Blob URL works. Validate returned URI accessibility as required by backend before draft creation.
9. Publisher must not repeat uncertain POST requests without reconciliation. Preserve remote ID as soon as it is known; archive only after verified published state.
10. Deliver `README.md`, `.env.example`, `config.example.yaml`, `docs/api-contract.md`, `docs/operations.md`, a concise `CLAUDE.md`, meaningful tests, and working CLI examples.
11. Prefer no network-dependent tests in standard CI; live paid/publish tests must be opt-in.
12. Document all remaining integration questions from §12 explicitly instead of guessing their answers.

---

### Technical references

- ElevenLabs Text to Speech API: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- ElevenLabs Text to Dialogue API: https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert/
- ElevenLabs Text to Dialogue guidance (recommended chunk sizes): https://elevenlabs.io/docs/overview/capabilities/text-to-dialogue
- ElevenLabs Python SDK/API metadata: https://elevenlabs.io/docs/api-reference/introduction/
- Ollama API: https://docs.ollama.com/api
- FFmpeg: https://ffmpeg.org/documentation.html
- Gumu-Gumu IdP discovery: https://iam.zambeziblue.com/.well-known/openid-configuration

**Note:** Gumu-Gumu episode create/publish routes are documented from the user-supplied contract; their live schema, authentication and media upload semantics have not been independently verified.
