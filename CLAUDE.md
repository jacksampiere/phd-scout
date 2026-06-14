# my_project

<brief project description>

## Template setup

If `my_project` placeholders are still present in this repo, this is a fresh
clone from the template. Complete setup before any other work:

1. Ask the user for the project name, a description, and whether they need tests.
2. Replace all placeholders throughout the repo:
   - `my_project` in `README.md`, `CLAUDE.md`, and `pyproject.toml`
   - `<brief project description>` in `README.md`, `CLAUDE.md`, and `pyproject.toml`
      - `pyproject.toml` description should be a short one-liner, not the full description
   - Rename the `my_project/` directory to the project name (snake case)
3. If no tests: remove `pytest` from dev dependencies in `pyproject.toml`, delete `tests/`,
   remove `[tool.pytest.ini_options]` from `pyproject.toml`, remove the
   `pytest` step from `.github/workflows/ci.yml`, remove the "Run tests" row
   from the Common commands table in `CLAUDE.md`, remove the "Tests live in
   `tests/`..." line from the Conventions section in `CLAUDE.md`, and remove
   the "Run tests" row and the "pytest" mention from the commands table and
   CI note in `README.md`.
4. Run `uv sync` to update the lockfile after any dependencies changes.
5. Run `bash scripts/setup-claude.sh` to wire up task-observer.
6. Run `pre-commit install` to wire up pre-commit hooks.
7. Remove this entire "Template setup" section from `CLAUDE.md`, along with the "Using this template" and "Claude setup" sections in `README.md`.

Do not proceed with any other work until these steps are complete.

## Task Observer (meta-skill)

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

| Task | Command |
|------|---------|
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |

## Conventions

- Dependencies are managed with `uv`. Add dependencies via `uv add <package>`, dev dependencies via `uv add --dev <package>`.
- All code must pass `ruff` before merging. Pre-commit hooks enforce this locally.
- Tests live in `tests/` and mirror the source structure.

## Project structure

<describe key files and directories here>
