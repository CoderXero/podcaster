# Operations

Every job keeps its manifest under `paths.working/<slug>/manifest.json`. State is written before the next irreversible step. A `DRAFT_CREATE_UNKNOWN` or `PUBLISH_UNKNOWN` state means the network outcome is ambiguous: reconcile with the server before retrying and do not repeat the POST blindly.

If Markdown is edited, run `podcaster script import <slug>` and then `podcaster script approve <slug>` before audio generation. Successful audio turn files are cached by text, voice, model, format, and settings; interrupted jobs can reuse verified files. Failed scratch files remain available for diagnosis, while successful job-local scratch files are removed after final MP3 validation.

For source safety, use the default `archive` disposition. A source is moved only after JSON and Markdown have been durably written and re-read. `delete` requires explicit confirmation and should be reserved for content with an independent backup.

Publisher failures before remote verification leave the local package in place. Archive failures after verified publication are local archive failures, not publication failures; the remote episode must never be republished merely because a local move failed.
