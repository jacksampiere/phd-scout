# phd_scout

Automated scouting for PhD opportunities — built to surface positions and labs that align with a specific research direction via recurring email digests.

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