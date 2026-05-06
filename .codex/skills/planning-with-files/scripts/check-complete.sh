#!/bin/bash
# Check if all phases in task_plan.md are complete
# Always exits 0 — uses stdout for status reporting
# Used by Stop hook to report task completion status

PLAN_FILE="${1:-${CODEX_PLAN_DIR:-.}/task_plan.md}"

if [ ! -f "$PLAN_FILE" ]; then
    echo "[planning-with-files] No task_plan.md found — no active planning session."
    exit 0
fi

# Count explicit phase headings. Anchor the match so examples in prose do not
# inflate the count.
TOTAL=$(grep -cE '^[[:space:]]*### Phase([[:space:]:]|$)' "$PLAN_FILE" || true)

# Check for **Status:** format first
COMPLETE=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*complete[[:space:]]*$' "$PLAN_FILE" || true)
IN_PROGRESS=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*in_progress[[:space:]]*$' "$PLAN_FILE" || true)
PENDING=$(grep -cE '^[[:space:]]*(-[[:space:]]*)?\*\*Status:\*\*[[:space:]]*pending[[:space:]]*$' "$PLAN_FILE" || true)

# Fallback: check for [complete] inline format if **Status:** not found
if [ "$COMPLETE" -eq 0 ] && [ "$IN_PROGRESS" -eq 0 ] && [ "$PENDING" -eq 0 ]; then
    COMPLETE=$(grep -cE '^[[:space:]]*-[[:space:]]*\[complete\]' "$PLAN_FILE" || true)
    IN_PROGRESS=$(grep -cE '^[[:space:]]*-[[:space:]]*\[in_progress\]' "$PLAN_FILE" || true)
    PENDING=$(grep -cE '^[[:space:]]*-[[:space:]]*\[pending\]' "$PLAN_FILE" || true)
fi

# Default to 0 if empty
: "${TOTAL:=0}"
: "${COMPLETE:=0}"
: "${IN_PROGRESS:=0}"
: "${PENDING:=0}"

if [ "$TOTAL" -eq 0 ]; then
    TOTAL=$((COMPLETE + IN_PROGRESS + PENDING))
fi

# Report status (always exit 0 — incomplete task is a normal state)
if [ "$COMPLETE" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    echo "[planning-with-files] ALL PHASES COMPLETE ($COMPLETE/$TOTAL). If the user has additional work, add new phases to task_plan.md before starting."
else
    echo "[planning-with-files] Task in progress ($COMPLETE/$TOTAL phases complete). Update progress.md before stopping."
    if [ "$IN_PROGRESS" -gt 0 ]; then
        echo "[planning-with-files] $IN_PROGRESS phase(s) still in progress."
    fi
    if [ "$PENDING" -gt 0 ]; then
        echo "[planning-with-files] $PENDING phase(s) pending."
    fi
fi
exit 0
