#!/usr/bin/env bash
set -euo pipefail

SKILL_COMMONS=~/.claude/skill-commons

if [ ! -d "$SKILL_COMMONS" ]; then
  echo "Error: $SKILL_COMMONS not found."
  echo "Run the task-observer setup prompt in a new repo first to initialise the central store."
  exit 1
fi

mkdir -p .claude/skills/task-observer
ln -sf "$SKILL_COMMONS/canonical-skills/task-observer/SKILL.md" \
       .claude/skills/task-observer/SKILL.md

echo "Done. Symlink created:"
ls -la .claude/skills/task-observer/SKILL.md

# Register this repo in skill-commons README
REPO_LINE="- \`$(pwd | sed "s|$HOME|~|")\` — $(date +%Y-%m-%d)"
if ! grep -qF "$(pwd | sed "s|$HOME|~|")" "$SKILL_COMMONS/README.md"; then
  sed -i '' "s|## Repos currently set up|## Repos currently set up\n\n$REPO_LINE|" \
      "$SKILL_COMMONS/README.md" 2>/dev/null || true
fi
