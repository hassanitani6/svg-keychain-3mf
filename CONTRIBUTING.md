# Contributing

Thanks for helping! Bug reports, test SVGs that break the tool, and ideas are very welcome as issues.

**Code pull requests are not accepted at the moment**, so that the author can keep offering commercial licences.
If you have a fix, describe it in an issue (a small diff in the issue is fine) and it may be added by the author.

## Set up

```bash
uv sync --extra render
uv run pytest
```

## Ground rules

- **Bug fixes come with a regression test** that fails before the fix and passes after it.
  `tools/triage/verify_fix.py` checks exactly that.
- Keep test inputs synthetic: draw a small SVG that shows the problem instead of adding real-world artwork.
- Don't add network access, telemetry or new required dependencies without opening an issue first.
- Most of the geometry lives in `src/svg_keychain_3mf/engine.py`; the command line is `cli.py`.

## Reporting bugs

Use the bug form and paste `svg-keychain doctor` output. Attach only files you are allowed to share publicly.
