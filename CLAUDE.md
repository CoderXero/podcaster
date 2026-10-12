# Podcaster contributor notes

- Python 3.12+; install with `pip install -e '.[dev]'` or `uv sync --extra dev`.
- JSON is canonical for scripts and must remain in sync with the rendered Markdown companion.
- Use atomic writes and preserve the source on every failure. Do not add live credentials or call paid/publication APIs in ordinary tests.
- Publisher must never invent blob URIs or retry an uncertain POST without reconciliation.
- Keep changes scoped to the requested stage and run `pytest`, `ruff check`, and `python -m compileall src` before handoff.
