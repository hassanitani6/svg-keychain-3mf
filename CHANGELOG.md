# Changelog

All notable changes to this project are listed here. Versions follow [Semantic Versioning](https://semver.org/).

## 0.1.2 — 2026-11-08

### Fixed
- `svg-keychain generate` no longer replaces files without asking. It refuses to write over the input file (for
  example `b_keychain.3mf` with `--outputs keychain`) and over any 3MF that already exists; pass the new
  `--overwrite` option to replace earlier outputs. Nothing is written if any planned output is refused.
- The desktop app never writes over the file it is reading, and says when it replaces an earlier output.
- 3MF files are written beside the target and then swapped in, so a crash or full disk can't leave a broken file
  in place of a good one.
- Very large inputs (SVG over 50 MB, 3MF parts over 512 MB), over-complex designs, and output-folder problems now
  give a clear error instead of a traceback.

## 0.1.1 — 2026-11-07

### Security
- Requires Python 3.11 or newer (Python 3.10 reached end of life in October 2026). This lets the optional renderer
  use Pillow 13, which fixes the known vulnerabilities in earlier Pillow releases.

### Licence
- From this version on, the project is licensed under PolyForm Noncommercial 1.0.0. Commercial use needs a licence
  from the author. Version 0.1.0 remains available under the MIT licence.

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
