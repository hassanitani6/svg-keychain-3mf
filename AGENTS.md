# Notes for coding agents

- Install: `uv sync --extra render`. Test: `uv run pytest` (about a minute).
- Package code is in `src/svg_keychain_3mf/`: `engine.py` (SVG parsing, geometry, 3MF writer, Tk app),
  `cli.py`, `doctor.py`.
- Every behaviour change needs a test in `tests/`; every bug fix needs a regression test that fails without the fix.
- Test inputs must be synthetic SVGs in `tests/fixtures/`.
- Do not add network calls, telemetry or new runtime dependencies.
- `tools/triage/` is maintainer tooling; it must stay read-only towards GitHub.
