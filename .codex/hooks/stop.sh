#!/bin/bash
# planning-with-files: Stop hook for Codex
# Reused from the Cursor integration; Codex adapts followup_message separately.

HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
PLAN_DIR="$(sh "${HOOK_DIR}/resolve-plan-dir.sh" 2>/dev/null)"
PLAN_FILE="${PLAN_DIR:+${PLAN_DIR}/}task_plan.md"

if [ ! -f "$PLAN_FILE" ]; then
    exit 0
fi

TOTAL=$(grep -cE '^[[:space:]]*### Phase([[:space:]:]|$)' "$PLAN_FILE" || true)
COMPLETE=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*complete[[:space:]]*$' "$PLAN_FILE" || true)
IN_PROGRESS=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*in_progress[[:space:]]*$' "$PLAN_FILE" || true)
PENDING=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*pending[[:space:]]*$' "$PLAN_FILE" || true)

if [ "$COMPLETE" -eq 0 ] && [ "$IN_PROGRESS" -eq 0 ] && [ "$PENDING" -eq 0 ]; then
    COMPLETE=$(grep -cE '^[[:space:]]*-[[:space:]]*\[complete\]' "$PLAN_FILE" || true)
    IN_PROGRESS=$(grep -cE '^[[:space:]]*-[[:space:]]*\[in_progress\]' "$PLAN_FILE" || true)
    PENDING=$(grep -cE '^[[:space:]]*-[[:space:]]*\[pending\]' "$PLAN_FILE" || true)
fi

: "${TOTAL:=0}"
: "${COMPLETE:=0}"
: "${IN_PROGRESS:=0}"
: "${PENDING:=0}"

if [ "$TOTAL" -eq 0 ]; then
    TOTAL=$((COMPLETE + IN_PROGRESS + PENDING))
fi

if [ "$COMPLETE" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    echo "{\"followup_message\": \"[planning-with-files] ALL PHASES COMPLETE ($COMPLETE/$TOTAL). If the user has additional work, add new phases to task_plan.md before starting.\"}"
    exit 0
fi

echo "{\"followup_message\": \"[planning-with-files] Task incomplete ($COMPLETE/$TOTAL phases done). Update progress.md, then read task_plan.md and continue working on the remaining phases.\"}"
exit 0
