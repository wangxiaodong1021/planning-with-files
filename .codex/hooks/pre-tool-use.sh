#!/bin/bash
# planning-with-files: Pre-tool-use hook for Codex
# Reused from the Cursor integration.

HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
PLAN_DIR="$(sh "${HOOK_DIR}/resolve-plan-dir.sh" 2>/dev/null)"
PLAN_FILE="${PLAN_DIR:+${PLAN_DIR}/}task_plan.md"

attestation_file_for() {
    if [ -n "$PLAN_DIR" ]; then
        printf "%s/.attestation\n" "$PLAN_DIR"
    else
        printf ".plan-attestation\n"
    fi
}

compute_hash() {
    target="$1"
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$target" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$target" | awk '{print $1}'
    else
        return 1
    fi
}

if [ -f "$PLAN_FILE" ]; then
    # Log plan context to stderr so the Codex adapter can surface it as systemMessage.
    ATTEST_FILE="$(attestation_file_for)"
    ATTEST=""
    ACTUAL=""
    if [ -f "$ATTEST_FILE" ]; then
        ATTEST="$(tr -d '[:space:]' < "$ATTEST_FILE" 2>/dev/null || true)"
        ACTUAL="$(compute_hash "$PLAN_FILE" 2>/dev/null || true)"
        if [ -z "$ACTUAL" ] || [ "$ACTUAL" != "$ATTEST" ]; then
            echo "[planning-with-files] [PLAN TAMPERED - injection blocked]" >&2
            echo "Plan directory: ${PLAN_DIR:-.}" >&2
            echo "expected=$ATTEST" >&2
            echo "actual=  ${ACTUAL:-unavailable}" >&2
            echo "Run /plan-attest after reviewing the current plan, or restore the file from backup/git." >&2
            echo '{"decision": "allow"}'
            exit 0
        fi
    fi
    echo "Plan directory: ${PLAN_DIR:-.}" >&2
    if [ -n "$ATTEST" ]; then
        echo "Plan-SHA256: $ATTEST" >&2
    fi
    head -30 "$PLAN_FILE" >&2
fi

echo '{"decision": "allow"}'
exit 0
