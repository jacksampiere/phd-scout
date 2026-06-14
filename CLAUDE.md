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
