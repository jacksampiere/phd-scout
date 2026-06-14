# my_project

<brief project description>

## Using this template

Open Claude Code and say "set up this repo from the template" — Claude will handle everything  automatically. Alternatively, follow the steps below:

1. Replace `my_project` throughout `README.md`, `CLAUDE.md`, and `pyproject.toml`, and rename the `my_project/` directory
2. Replace `<brief project description>` in `README.md`, `CLAUDE.md`, and `pyproject.toml`
3. Run `bash scripts/setup-claude.sh` to wire up task-observer (see below)

## Claude setup

This repo uses [task-observer](https://github.com/rebelytics/one-skill-to-rule-them-all) — a meta-skill that runs silently during Claude Code sessions, logs skill improvement opportunities to a central store, and applies them in periodic reviews. Over time, it builds a self-improving skill library that carries across every repo you work in.

The `CLAUDE.md` block activates it at the start of each session. To wire it into a new repo cloned from this template, run `bash scripts/setup-claude.sh` (requires the central store to already exist — see the task-observer repo for first-time setup).

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

Ruff and pytest are enforced by CI on push and PRs to main:

| Task | Command |
|------|---------|
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |
