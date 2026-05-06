#!/bin/sh
# planning-with-files: set or display the active plan pointer.
#
# Usage:
#   set-active-plan.sh <plan_id>   — pin .planning/.active_plan to plan_id
#   set-active-plan.sh --attach-session <session_id> <plan_id>
#   set-active-plan.sh             — print the current active plan (if any)
#
# The active plan is stored in .planning/.active_plan and is read by
# resolve-plan-dir.sh when no $PLAN_ID env var is set.

set -e

PLAN_ROOT="${PWD}/.planning"
PLAN_CONTAINER="${PLAN_ROOT}/plans"
ACTIVE_FILE="${PLAN_ROOT}/.active_plan"

plan_dir_for_id() {
    plan_id="$1"
    if [ -d "${PLAN_CONTAINER}/${plan_id}" ]; then
        printf "%s\n" "${PLAN_CONTAINER}/${plan_id}"
        return 0
    fi
    if [ -d "${PLAN_ROOT}/${plan_id}" ]; then
        printf "%s\n" "${PLAN_ROOT}/${plan_id}"
        return 0
    fi
    return 1
}

ATTACH_SESSION_ID=""
if [ "${1:-}" = "--attach-session" ]; then
    ATTACH_SESSION_ID="${2:-}"
    shift 2
fi

# No args → show current active plan
if [ "${1:-}" = "" ]; then
    if [ -f "${ACTIVE_FILE}" ]; then
        plan_id="$(tr -d '\r\n' < "${ACTIVE_FILE}")"
        plan_dir="$(plan_dir_for_id "${plan_id}" 2>/dev/null || true)"
        if [ -n "${plan_id}" ] && [ -n "${plan_dir}" ]; then
            echo "Active plan: ${plan_id}"
            echo "Path: ${plan_dir}"
        elif [ -n "${plan_id}" ]; then
            echo "Active plan pointer: ${plan_id} (directory not found — stale pointer)"
        else
            echo "No active plan set."
        fi
    else
        echo "No active plan set."
    fi
    exit 0
fi

PLAN_ID="$1"
PLAN_DIR="$(plan_dir_for_id "${PLAN_ID}" 2>/dev/null || true)"

if [ -z "${PLAN_DIR}" ] || [ ! -d "${PLAN_DIR}" ]; then
    echo "Error: plan directory not found for: ${PLAN_ID}" >&2
    echo "Run: init-session.sh \"${PLAN_ID}\" to create it, or check .planning/plans/ for available plans." >&2
    exit 1
fi

if [ ! -f "${PLAN_DIR}/task_plan.md" ]; then
    echo "Error: plan directory has no task_plan.md: ${PLAN_DIR}" >&2
    exit 1
fi

mkdir -p "${PLAN_ROOT}"
printf "%s\n" "${PLAN_ID}" > "${ACTIVE_FILE}"

if [ -n "${ATTACH_SESSION_ID}" ]; then
    mkdir -p "${PLAN_ROOT}/sessions"
    cat > "${PLAN_ROOT}/sessions/${ATTACH_SESSION_ID}.json" << EOF
{
  "schema_version": 1,
  "session_id": "${ATTACH_SESSION_ID}",
  "plan_id": "${PLAN_ID}",
  "plan_dir": "${PLAN_DIR}",
  "mode": "attached",
  "attached_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF
fi

echo "Active plan set to: ${PLAN_ID}"
echo "Path: ${PLAN_DIR}"
if [ -n "${ATTACH_SESSION_ID}" ]; then
    echo "Session attached: ${PLAN_ROOT}/sessions/${ATTACH_SESSION_ID}.json"
fi
echo ""
echo "To pin this terminal session only:"
echo "  export PLAN_ID=${PLAN_ID}"
