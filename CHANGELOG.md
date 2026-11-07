# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.1.1 — unreleased

### Fixed
- Windows: text files are read and written as UTF-8, so triage reports and SVG text are no longer garbled.
- Windows: `svg-keychain generate` no longer crashes after writing the 3MF when the file name has characters the
  terminal encoding can't show (for example Arabic or Chinese names).
- `--thickness` on keychains now prints a note instead of being silently ignored (keychains use a fixed relief),
  and the `--merge-threshold` help describes the real RGB scale.
- Maintainer triage tool: recognises bot-authored issues in the form `gh` actually returns, says so when every AI
  citation was rejected, and removes more kinds of access token.

### Documentation
- README is more precise about clean-up (some steps are keychain-only), the automatic backing plate for keychains
  with islands, text and gradients, the magnet message, crash logs, and what the triage tool can and can't redact.

## 0.1.0 — 2026-11-07

First public release: SVG to multi-colour 3MF keychains, plaques and fridge magnets for Bambu Studio, with a
desktop app, a command line, the `doctor` report, tests and CI.
