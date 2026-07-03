#!/usr/bin/env bash
# Surface factory state at session start; silent when repo has no .factory/.
set -euo pipefail
[ -d ".factory" ] || exit 0
CLI="${CLAUDE_PLUGIN_ROOT}/scripts/factory/factory.py"
echo "This repo is a Factory target. Pipeline state:"
python3 "$CLI" --repo . status 2>/dev/null || echo "(factory state unreadable - run: factory validate)"
NEXT=$(python3 "$CLI" --repo . next 2>/dev/null || true)
echo "Next actionable: ${NEXT:-none}"
if ls docs/factory/packets/*.md >/dev/null 2>&1; then
  echo "Packets awaiting human review: $(ls docs/factory/packets/*.md | tr '\n' ' ')"
fi
echo "Use /factory:run to advance the pipeline. Skills: factory-dispatch."
