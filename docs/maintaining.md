# Maintaining

A short routine for keeping issues moving without automation you have to babysit.

## Labels

| Label | Meaning |
|---|---|
| `needs-triage` | New; added by the issue forms. Remove once you have read it. |
| `bug`, `enhancement`, `question`, `documentation` | What kind of issue it is. |
| `needs-info` | Waiting on the reporter. Close after 30 days without a reply. |
| `duplicate-candidate` | Looks like another issue; link it and close once confirmed. |
| `svg-reader`, `3mf-output`, `gui`, `packaging`, `printability` | Area of the code. |

## Weekly routine (about 15 minutes)

1. Open the `needs-triage` list.
2. For each issue, run the free checks:
   `python tools/triage/triage.py fetch N && python tools/triage/triage.py check N`
   and read `.triage/N/report.md`. It lists missing information, possible duplicates, version mismatches,
   personal details to remove and anything that looks like an attempt to manipulate an AI.
3. Reproduce with the reporter's SVG (or a redrawn one) and `svg-keychain generate`.
4. Reply, label, and remove `needs-triage`.

The manual route always works; the helper in step 2 and the AI step below are optional.

## Optional: AI-assisted reading

`python tools/triage/triage.py investigate N --dry-run` writes the exact text that would be sent to
`.triage/N/prompt.txt` without sending anything — read it first. Then
`python tools/triage/triage.py investigate N --ai --issues issues.json` asks Claude to point at the code most
likely involved. What it does and does not do:

- Runs **only** when you type the command, on your computer. It never posts, labels, closes or edits anything.
- Sends the issue title and body to Anthropic's API, after removing email addresses, phone numbers, home-folder
  paths and tokens. It refuses to run on incomplete reports, bot-authored issues, or text that looks like
  prompt injection.
- The model gets only the Read, Grep and Glob tools (no shell, no web), and your shell's GitHub tokens are not
  passed to it. Those tools are not a sandbox: assume it could read any file your user account can, and that
  whatever it reads is sent to Anthropic. Run this step from a user account or container that holds only this
  repository.
- Every finding must cite a file, line range and exact quote. The script checks each citation against the code and
  drops any that do not match; if nothing survives, the report says so.
- Treat the report as a lead, not an answer. If you quote it publicly, say it was AI-assisted.

**Cost.** Uses an Anthropic API key (`ANTHROPIC_API_KEY`), billed per use — `--bare` mode does not use a Claude
subscription. Limits in `tools/triage/config.json`: `max_budget_usd_per_run` (passed to the CLI) and
`monthly_budget_usd` (checked against `.triage/ledger.jsonl` before each run, leaving room for every retry).
Every attempt is recorded: a successful one at the cost the CLI reports, a failed, timed-out or unreported one
at the full per-run budget. `"model": "sonnet"` follows Anthropic's current Sonnet model; pin a full model ID
if you need runs to stay comparable. Also set a spending limit on the key itself in the Anthropic Console:
that is the only limit enforced outside this script.

**Off switch.** Any of: `export TRIAGE_DISABLED=1`, `touch .triage/STOP`, or `"enabled": false` in the config.
To remove it completely, delete the API key in the Console.

**Retention.** `.triage/` is git-ignored and stays on your computer. It contains copies of issue text. Delete a
folder once the issue is closed, or clear everything older than 30 days:
`find .triage -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -r {} +`

## Checking a fix

```bash
git worktree add ../before main
git worktree add ../after my-fix-branch
python tools/triage/verify_fix.py --before ../before --after ../after --test tests/test_engine.py::test_name
```

It passes only when the new test fails on `main`, passes on the fix, and the full suite passes on the fix.
Merging stays a manual decision.

## Releasing

1. All CI checks green on `main`.
2. Bump `__version__` in `src/svg_keychain_3mf/__init__.py` and `version` in `pyproject.toml`.
3. `uv lock`, commit, tag `vX.Y.Z`, push the tag, write release notes by hand.
4. Install the tag in a fresh environment and run `svg-keychain doctor` and one `generate`.

## Updating pinned GitHub Actions

Actions in `.github/workflows/` are pinned to full commit SHAs. Dependabot proposes updates monthly. Before
merging one, check that the new SHA belongs to the action's own repository (not a fork) and read its release notes.
