# Operations guide

Everything needed to set up, run, and manage phd_scout. For what the tool *is*, see the
[README](../README.md).

## 1. First-time setup

```shell
git clone https://github.com/jacksampiere/phd-scout.git
cd phd-scout
uv sync && source .venv/bin/activate   # install deps + activate venv
pre-commit install                     # ruff hooks (enforced locally + in CI)
cp profile.template.md profile.md      # then edit with your research interests
```

`profile.md` is gitignored — it holds your personal positioning and is the single source of
truth for scoring (rubric, axes, thresholds). Retuning the search is a one-file edit here.

## 2. GitHub Actions secrets

The scheduled monitor ([`.github/workflows/daily.yml`](../.github/workflows/daily.yml)) reads
**five** secrets. Set them once with the `gh` CLI (authenticated, run from the repo):

```shell
gh secret set ANTHROPIC_API_KEY        # Claude API key
gh secret set GMAIL_ADDRESS            # sending Gmail account
gh secret set GMAIL_APP_PASSWORD       # 16-char Gmail app password (requires 2FA on the account)
gh secret set DIGEST_RECIPIENT         # where the digest goes; optional, defaults to GMAIL_ADDRESS
gh secret set PROFILE_MD < profile.md  # the full scoring rubric (see note below)
gh secret list                         # confirm all five are present
```

**Why `PROFILE_MD` is a secret:** `profile.md` is gitignored, so it does not exist in the CI
checkout. The workflow writes the secret to disk before the run. This keeps the rubric private
while still feeding it to the scorer.

**Keep it in sync:** every time you edit `profile.md` locally, re-upload it or CI keeps
scoring against the old rubric:
> ```shell
> gh secret set PROFILE_MD < profile.md
> ```

## 3. Running locally

Local runs read the same env vars from a `.envrc` file (gitignored, loaded via `python-dotenv`):

```
ANTHROPIC_API_KEY=...
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...
DIGEST_RECIPIENT=...
```

Staged flags, cheapest → most complete:

| Command | What it does |
| --- | --- |
| `uv run python -m phd_scout --dry-run` | Fetch and print raw listings per source. No scoring, no email, no state. |
| `uv run python -m phd_scout --score [--limit N]` | Fetch + score against `profile.md`, print scores + justifications. No email, no state. `--limit` caps how many are scored (sampled across sources). |
| `uv run python -m phd_scout --preview [--limit N]` | Full pipeline, but **print** the digest instead of sending. No email, no state write. |
| `uv run python -m phd_scout --send-test` | Send one synthetic digest to verify Gmail SMTP. No fetch, no scoring. |
| `uv run python -m phd_scout` | **Real run:** fetch → dedup → score new → email matches → update `seen.json`. |

A local run uses a **local** `seen.json` at the repo root, completely independent from the CI
cache (see §6) — running locally never touches or syncs CI state.

## 4. The scheduled workflow

`daily.yml` runs daily at **15:00 UTC (~7 AM Pacific)** and can also be triggered on demand.

```shell
gh workflow run daily.yml     # manual trigger (also: Actions tab → Daily digest → Run workflow)
```

Steps: checkout → `uv sync` → restore dedup state from cache → write `profile.md` from the
secret → run the monitor → publish the state snapshot as an artifact.

## 5. Verifying a run

```shell
gh run watch                             # live step-by-step status (✓/∗), not log contents
gh run view <run-id> --web               # open in browser — the UI streams step logs live
gh run view <run-id> --log               # full logs (after the run finishes)
gh run view <run-id> --log | grep -i listing   # e.g. the "N listings found" line
```

- **Watch logs while a run is in progress:** use the **web UI** (`--web`) and expand the
  running step — the CLI `--log` only populates once a step completes.
- **First CI run surfaces a lot.** The cache starts empty, so run #1 treats every listing as
  new and emails a large one-time digest. Dedup kicks in from run #2. To confirm dedup, trigger
  a second run and check that it surfaces nothing new.

## 6. State management (dedup)

`seen.json` (the set of already-seen listing IDs) is **gitignored** and lives in the **GitHub
Actions cache**, not in the repo — this keeps the public repo a clean tool with no personal
search data. It is written only on a clean pass, so a failed run never corrupts it.

The cache is opaque, so every run also publishes `seen.json` as a downloadable artifact:

```shell
gh run download <run-id> -n seen-json   # fetch the state snapshot for a run
```

- **Viewing:** download the artifact (above), or Actions tab → a run → Artifacts.
- **Self-healing:** if the cache is ever evicted (unused >7 days, or repo cache >10 GB — neither
  expected for a daily job on a tiny file), the next run starts fresh: one duplicate digest,
  then normal.
- **Editing CI state by hand is not supported** — there's no clean way to push a local
  `seen.json` back into the cache. You rarely need to; rely on self-heal.

## 7. Updating the search

Edit `profile.md` (rubric, axes, §3 thresholds, §6b position types, §7 geography, §8 known
labs — all defined there, not in code), then **re-upload the secret** so CI picks it up:

```shell
gh secret set PROFILE_MD < profile.md
```

## 8. Troubleshooting

- **A run failed (red).** GitHub emails you a terse notice; the full error/traceback is in the
  logs for 90 days: `gh run view <run-id> --log-failed`.
- **The pipeline fails safe.** Fatal errors — bad/expired `ANTHROPIC_API_KEY`, exhausted API
  credit, Gmail SMTP auth — abort *before* `seen.json` is written, so the next run retries the
  same listings. Fix the underlying secret and re-trigger.
- **Per-listing errors don't fail the run.** A malformed listing or transient fetch error is
  logged and skipped, so a failed run is never caused by one bad listing.
- **CI scoring seems out of date.** You edited `profile.md` but didn't re-upload `PROFILE_MD`
  (§2).
- **A source returns nothing.** A dead/blocked source (e.g. FindAPhD is Cloudflare-blocked) is
  logged and skipped by design — it never crashes the run. The digest email nudges a manual
  FindAPhD check.