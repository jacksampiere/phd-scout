# phd_scout

Automated scouting for PhD opportunities — built to surface positions and labs that align with a specific research direction via recurring email digests.

## Task Observer (meta-skill)

Note: this requires .claude/skills/task-observer/ and refers to a local skill installed via symlink (not committed). Source: https://github.com/rebelytics/one-skill-to-rule-them-all

At the start of any task-oriented session — any interaction where you will use
tools and produce deliverables — invoke the task-observer skill before beginning
work. This ensures skill improvement opportunities are captured throughout the
session.

When loading any skill, check the observation log at
`~/.claude/skill-commons/skill-observations/log.md` for OPEN observations tagged
to that skill. Apply their insights to the current work, even if the skill file
hasn't been updated yet.

When the user signals they are wrapping up or archiving a session (e.g. "done",
"that's all", "wrapping up", "archive this"), proactively remind them to ask
"Any observations logged?" before closing.

## Setup

```shell
uv sync && source .venv/bin/activate
```

## Common commands

| Task                      | Command                                |
| ------------------------- | -------------------------------------- |
| Run tests                 | `uv run pytest`                        |
| Lint                      | `uv run ruff check .`                  |
| Format                    | `uv run ruff format .`                 |
| Run the monitor (dry run) | `uv run python -m phd_scout --dry-run` |
| Run the monitor           | `uv run python -m phd_scout`           |

## Conventions

- Dependencies are managed with `uv`. Add dependencies via `uv add <package>`, dev dependencies via `uv add --dev <package>`.
- All code must pass `ruff` before merging. Pre-commit hooks enforce this locally.
- Tests live in `tests/` and mirror the source structure.
- Python 3.12 (`>=3.12, <3.13`), line length 88, ruff lint selects E/F/I.

## Project structure

```
phd_scout/
├── __init__.py
├── __main__.py        # entrypoint: python -m phd_scout [--dry-run]
├── sources.py         # one fetcher per job board → normalized listings
├── scoring.py         # Claude API scoring against profile.md
├── state.py           # seen.json read/write + dedup
└── digest.py          # email formatting + Gmail SMTP send
tests/                 # mirror source: test_scoring.py, test_state.py, ...
.github/workflows/
├── ci.yml             # existing: ruff + pytest on push/PR
└── daily.yml          # new: scheduled monitor run
profile.md             # scoring rubric — GITIGNORED (personal)
profile.template.md    # sanitized committed example
seen.json              # auto-updated state, committed back by daily.yml
labmap/                # phase 2 — OpenAlex lab map, not built yet
```

## What this is — two subsystems

1. **Rolling monitor** (primary, ongoing) — `daily.yml` runs `python -m phd_scout`, which
   fetches new listings, scores them against `profile.md`, and emails a digest of matches.
   Zero action required from the user beyond reading.
2. **Lab map** (secondary, one-time) — `labmap/` uses the OpenAlex API to find labs
   publishing on relevant topics, scored and ranked into a browsable table. Build _after_ the
   monitor works.

## Decisions (don't relitigate without reason)

- **Hosting / scheduling:** GitHub Actions cron (`daily.yml`). No server. Mirror the `setup-uv`
  pattern from `ci.yml` for consistency.
- **Email out:** Gmail SMTP via app password (requires 2FA), stored as a GitHub Actions secret.
- **Scoring model:** default `claude-sonnet-4-6` (low daily volume, quality > per-call cost) in
  one config constant; `claude-haiku-4-5-20251001` is the one-line cost swap.
- **State:** committed `seen.json`; `daily.yml` needs `contents: write` to push it back.
- **Deps:** add via `uv add` — `requests`, `feedparser`, `anthropic` (runtime); `python-dotenv`
  already present. No `requirements.txt`.

## Hard rules

- **`profile.md` is gitignored.** Make sure it's added to `.gitignore` before the first commit. Commit a
  sanitized `profile.template.md` so the public repo is self-explanatory.
- **No secrets in code or commits** — API key, Gmail address, app password → GitHub secrets only.

## Source verification

Don't trust hardcoded feed URLs. For each candidate source (FindAPhD, EURAXESS, jobs.ac.uk,
Nature Careers, others), verify the current feed format live, confirm it parses, and adapt —
prefer official RSS/APIs over scraping. A dead/blocked source logs and is skipped; it never
crashes the run. EURAXESS has had a structured API worth checking.

## Scoring contract

`profile.md` defines the rubric. Implement scoring as: send full `profile.md` + listing
text to the model, get structured JSON `{domain_fit, robustness, robustness_forms, justification,
surface}`, parse robustly (strip fences; skip-not-crash on malformed output). Mirror the §3
threshold logic in `scoring.py` but keep it a one-place edit.

## Working style

- **Diagnostics before automation.** Stage it: feed parsing prints raw listings → scoring prints
  scores+justifications on real listings (eyeball calibration vs `profile.md`) → email → cron.
  Lock each contract before the next.
- **Targeted edits over rewrites.** Surgical changes; don't rewrite working modules.
- **Honest pushback over validation.** If a choice here is wrong, say so.
- **Fail safe.** Degrade gracefully + log; an empty-but-successful run is fine, a silent failure
  is not.

## Optional — agentic tooling

The manual feedback loop (user edits `profile.md` §3/§9) is the baseline and is fine alone. Only
if it earns its place: a "retune-profile" skill that turns free-text digest feedback into proposed
targeted edits to `profile.md`. Build it following the existing `task-observer` / `skill-commons`
pattern — don't invent a parallel system, and don't force it.
