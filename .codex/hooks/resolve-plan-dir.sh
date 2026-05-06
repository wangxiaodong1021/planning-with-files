#!/bin/sh
# planning-with-files: resolve active plan directory.
#
# Resolution order:
#   1. $CODEX_PLAN_DIR env var if it contains task_plan.md
#   2. $PLAN_ID env var → ./.planning/plans/$PLAN_ID/ or ./.planning/$PLAN_ID/
#   3. ./.planning/.active_plan content → matching plan dir
#   4. Newest ./.planning/plans/<dir>/, then ./.planning/<dir>/ by mtime
#   5. Otherwise empty stdout (caller falls back to legacy ./task_plan.md)
#
# Always exits 0. Never errors out the agent loop.
#
# Usage:
#   PLAN_DIR="$(sh scripts/resolve-plan-dir.sh)"
#   PLAN_FILE="${PLAN_DIR:+$PLAN_DIR/}task_plan.md"

set -u

PLAN_ROOT="${1:-${PWD}/.planning}"
PLAN_CONTAINER="${PLAN_ROOT}/plans"
ACTIVE_FILE="${PLAN_ROOT}/.active_plan"

emit_if_plan_dir() {
    candidate="$1"
    [ -d "${candidate}" ] || return 1
    [ -f "${candidate}/task_plan.md" ] || return 1
    printf "%s\n" "${candidate}"
    return 0
}

resolve_from_codex_plan_dir() {
    plan_dir="${CODEX_PLAN_DIR:-}"
    [ -z "${plan_dir}" ] && return 1
    case "${plan_dir}" in
        /*) candidate="${plan_dir}" ;;
        *) candidate="${PWD}/${plan_dir}" ;;
    esac
    emit_if_plan_dir "${candidate}"
}

resolve_from_env() {
    plan_id="${PLAN_ID:-}"
    [ -z "${plan_id}" ] && return 1
    candidate="${PLAN_CONTAINER}/${plan_id}"
    emit_if_plan_dir "${candidate}" && return 0
    candidate="${PLAN_ROOT}/${plan_id}"
    emit_if_plan_dir "${candidate}" && return 0
    return 1
}

resolve_from_active_file() {
    [ -f "${ACTIVE_FILE}" ] || return 1
    plan_id="$(tr -d '\r\n' < "${ACTIVE_FILE}")"
    [ -z "${plan_id}" ] && return 1
    candidate="${PLAN_CONTAINER}/${plan_id}"
    emit_if_plan_dir "${candidate}" && return 0
    candidate="${PLAN_ROOT}/${plan_id}"
    emit_if_plan_dir "${candidate}" && return 0
    return 1
}

resolve_latest_dir_in() {
    search_root="$1"
    [ -d "${search_root}" ] || return 1
    # Portable newest-mtime selector. Avoid `ls -t` BSD/GNU drift.
    # Only consider dirs that contain task_plan.md — skips system dirs like sessions/.
    latest=""
    latest_mtime=0
    for entry in "${search_root}"/*/; do
        [ -d "${entry}" ] || continue
        # Strip trailing slash
        clean="${entry%/}"
        # Skip hidden dirs
        case "$(basename "${clean}")" in
            .*) continue ;;
        esac
        # Skip dirs that are not plan dirs
        [ -f "${clean}/task_plan.md" ] || continue
        mtime="$(date -r "${clean}" +%s 2>/dev/null || stat -c '%Y' "${clean}" 2>/dev/null || echo 0)"
        if [ "${mtime}" -gt "${latest_mtime}" ] 2>/dev/null; then
            latest_mtime="${mtime}"
            latest="${clean}"
        fi
    done
    if [ -n "${latest}" ]; then
        printf "%s\n" "${latest}"
        return 0
    fi
    return 1
}

if resolve_from_codex_plan_dir; then exit 0; fi
if resolve_from_env; then exit 0; fi
if resolve_from_active_file; then exit 0; fi
if resolve_latest_dir_in "${PLAN_CONTAINER}"; then exit 0; fi
if resolve_latest_dir_in "${PLAN_ROOT}"; then exit 0; fi
exit 0
