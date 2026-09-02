# phd_scout

Automated scouting for PhD opportunities — built to surface positions and labs that align with a specific research direction via recurring email digests.

## What it does

**Rolling monitor.** A daily GitHub Actions job fetches new PhD listings from job
boards, scores each against a research-interest rubric using the Claude API, and emails a short digest of only the matches — each with its scores, a one-line justification, and which
robustness property it exhibits. New listings only; nothing already seen.

## How it works

```
GitHub Actions (daily cron, daily.yml)
  └─ python -m phd_scout
       ├─ sources.py   fetch new listings from job-board feeds/APIs
       ├─ scoring.py   score each via Claude API against the research profile
       ├─ state.py     skip anything already seen (seen.json, kept in the Actions cache)
       └─ digest.py    email a digest of matches (Gmail SMTP)
```

Scoring is driven entirely by `profile.md` — the rubric, axes, and thresholds all live there.
Retuning the search is a one-file edit.

## Setup

Install uv:

```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install dependencies and activate:

```shell
uv sync && source .venv/bin/activate
```

Wire up pre-commit hooks:

```shell
pre-commit install
```

Create your profile from the template (this file is gitignored — it holds personal positioning):

```shell
cp profile.template.md profile.md   # then edit profile.md with your research interests
```

The scheduled monitor needs five GitHub Actions secrets (`ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`,
`GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT`, `PROFILE_MD`) and a one-time verification run. See
**[docs/operations.md](docs/operations.md)** for the full setup, run, state-management, and
troubleshooting guide.

Ruff and pytest are enforced by CI on push and PRs to main:

| Task                      | Command                                |
| ------------------------- | -------------------------------------- |
| Run tests                 | `uv run pytest`                        |
| Lint                      | `uv run ruff check .`                  |
| Format                    | `uv run ruff format .`                 |
| Run the monitor (dry run) | `uv run python -m phd_scout --dry-run` |

---

_A personal research tool. The scoring profile (`profile.md`) and dedup state (`seen.json`) are intentionally kept out of version control._
