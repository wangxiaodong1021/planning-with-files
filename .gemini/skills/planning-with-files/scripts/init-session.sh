#!/usr/bin/env bash
# Initialize planning files for a new session.
#
# Usage:
#   ./init-session.sh                              # legacy: root-level task_plan.md, findings.md, progress.md
#   ./init-session.sh [--template TYPE]            # legacy with template choice
#   ./init-session.sh "Backend Refactor"           # slug mode: .planning/plans/<date>-backend-refactor/
#   ./init-session.sh --plan-dir                   # slug mode with auto-generated untitled-<short> name
#   ./init-session.sh --plan-dir "Quick Spike"     # slug mode, explicit slug
#   ./init-session.sh --attach-session <id> "Task" # create plan and bind a Codex session to it
#
# Legacy mode (zero positional args, no --plan-dir) preserves v1.x behavior so
# upgrades stay non-breaking. Slug mode addresses parallel multi-task isolation
# (issue #148) by writing each plan under .planning/plans/<date>-<slug>/ and pinning
# .planning/.active_plan so resolve-plan-dir.sh can find it.

set -e

TEMPLATE="default"
PROJECT_NAME=""
USE_PLAN_DIR=0
ATTACH_SESSION_ID="${PWF_SESSION_ID:-${CODEX_SESSION_ID:-${CODEX_THREAD_ID:-}}}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --template|-t)
            TEMPLATE="$2"
            shift 2
            ;;
        --plan-dir)
            USE_PLAN_DIR=1
            shift
            ;;
        --attach-session)
            ATTACH_SESSION_ID="$2"
            USE_PLAN_DIR=1
            shift 2
            ;;
        *)
            if [ -z "$PROJECT_NAME" ]; then
                PROJECT_NAME="$1"
            else
                PROJECT_NAME="$PROJECT_NAME $1"
            fi
            shift
            ;;
    esac
done

DATE=$(date +%Y-%m-%d)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE_DIR="$SKILL_ROOT/templates"

if [ "$TEMPLATE" != "default" ] && [ "$TEMPLATE" != "analytics" ]; then
    echo "Unknown template: $TEMPLATE (available: default, analytics). Using default."
    TEMPLATE="default"
fi

# Slug mode triggers when a project name was given OR --plan-dir was passed.
SLUG_MODE=0
if [ -n "$PROJECT_NAME" ] || [ "$USE_PLAN_DIR" -eq 1 ]; then
    SLUG_MODE=1
fi

slugify() {
    # Lowercase, non-alphanumerics → '-', collapse repeats, trim leading/trailing '-'
    printf '%s' "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -e 's/[^a-z0-9]/-/g' -e 's/-\{2,\}/-/g' -e 's/^-//' -e 's/-$//' \
        | cut -c1-40
}

short_uuid() {
    # Probe each candidate: command -v alone is not enough on Windows because
    # App Execution Aliases report presence but exit non-zero when run.
    _py="${PYTHON_BIN:-}"
    if [ -z "$_py" ]; then
        for _c in python3 python py; do
            if command -v "$_c" >/dev/null 2>&1 && "$_c" -c "import uuid" >/dev/null 2>&1; then
                _py="$_c"
                break
            fi
        done
    fi
    if [ -n "$_py" ]; then
        "$_py" -c "import uuid; print(uuid.uuid4().hex[:8])"
        return
    fi
    if command -v uuidgen >/dev/null 2>&1; then
        uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | cut -c1-8
        return
    fi
    # Last-ditch: seconds timestamp as 8 hex chars
    printf '%08x' "$(date +%s)" | cut -c1-8
}

write_default_task_plan() {
    cat > "$1" << 'EOF'
# Task Plan: [Brief Description]

## Goal
[One sentence describing the end state]

## Current Phase
Phase 1

## Phases

### Phase 1: Requirements & Discovery
- [ ] Understand user intent
- [ ] Identify constraints
- [ ] Document in findings.md
- **Status:** in_progress

### Phase 2: Planning & Structure
- [ ] Define approach
- [ ] Create project structure
- **Status:** pending

### Phase 3: Implementation
- [ ] Execute the plan
- [ ] Write to files before executing
- **Status:** pending

### Phase 4: Testing & Verification
- [ ] Verify requirements met
- [ ] Document test results
- **Status:** pending

### Phase 5: Delivery
- [ ] Review outputs
- [ ] Deliver to user
- **Status:** pending

## Decisions Made
| Decision | Rationale |
|----------|-----------|

## Errors Encountered
| Error | Resolution |
|-------|------------|
EOF
}

write_default_findings() {
    cat > "$1" << 'EOF'
# Findings & Decisions

## Requirements
-

## Research Findings
-

## Technical Decisions
| Decision | Rationale |
|----------|-----------|

## Issues Encountered
| Issue | Resolution |
|-------|------------|

## Resources
-
EOF
}

write_default_progress() {
    local date_value="$1"
    local target="$2"
    cat > "$target" << EOF
# Progress Log

## Session: $date_value

### Current Status
- **Phase:** 1 - Requirements & Discovery
- **Started:** $date_value

### Actions Taken
-

### Test Results
| Test | Expected | Actual | Status |
|------|----------|--------|--------|

### Errors
| Error | Resolution |
|-------|------------|
EOF
}

json_escape() {
    _py="${PYTHON_BIN:-}"
    if [ -z "$_py" ]; then
        for _c in python3 python py; do
            if command -v "$_c" >/dev/null 2>&1 && "$_c" -c "import json" >/dev/null 2>&1; then
                _py="$_c"
                break
            fi
        done
    fi
    if [ -n "$_py" ]; then
        "$_py" -c 'import json,sys; print(json.dumps(sys.argv[1])[1:-1])' "$1"
    else
        printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
    fi
}

write_metadata() {
    local plan_dir="$1"
    local plan_id="$2"
    local title="$3"
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    cat > "${plan_dir}/metadata.json" << EOF
{
  "schema_version": 1,
  "plan_id": "$(json_escape "$plan_id")",
  "title": "$(json_escape "${title:-untitled}")",
  "status": "in_progress",
  "created_at": "$now",
  "updated_at": "$now"
}
EOF
}

attach_session() {
    local session_id="$1"
    local plan_id="$2"
    local plan_dir="$3"
    [ -n "$session_id" ] || return 0
    local sessions_dir="${PWD}/.planning/sessions"
    local now
    now="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    mkdir -p "$sessions_dir"
    cat > "${sessions_dir}/${session_id}.json" << EOF
{
  "schema_version": 1,
  "session_id": "$(json_escape "$session_id")",
  "plan_id": "$(json_escape "$plan_id")",
  "plan_dir": "$(json_escape "$plan_dir")",
  "mode": "attached",
  "attached_at": "$now"
}
EOF
}

write_analytics_progress() {
    local date_value="$1"
    local target="$2"
    cat > "$target" << EOF
# Progress Log

## Session: $date_value

### Current Status
- **Phase:** 1 - Data Discovery
- **Started:** $date_value

### Actions Taken
-

### Query Log
| Query | Result Summary | Interpretation |
|-------|---------------|----------------|

### Errors
| Error | Resolution |
|-------|------------|
EOF
}

create_files_in() {
    local target_dir="$1"
    local plan_path="$target_dir/task_plan.md"
    local findings_path="$target_dir/findings.md"
    local progress_path="$target_dir/progress.md"

    if [ ! -f "$plan_path" ]; then
        if [ "$TEMPLATE" = "analytics" ] && [ -f "$TEMPLATE_DIR/analytics_task_plan.md" ]; then
            cp "$TEMPLATE_DIR/analytics_task_plan.md" "$plan_path"
        else
            write_default_task_plan "$plan_path"
        fi
        echo "Created $plan_path"
    else
        echo "$plan_path already exists, skipping"
    fi

    if [ ! -f "$findings_path" ]; then
        if [ "$TEMPLATE" = "analytics" ] && [ -f "$TEMPLATE_DIR/analytics_findings.md" ]; then
            cp "$TEMPLATE_DIR/analytics_findings.md" "$findings_path"
        else
            write_default_findings "$findings_path"
        fi
        echo "Created $findings_path"
    else
        echo "$findings_path already exists, skipping"
    fi

    if [ ! -f "$progress_path" ]; then
        if [ "$TEMPLATE" = "analytics" ]; then
            write_analytics_progress "$DATE" "$progress_path"
        else
            write_default_progress "$DATE" "$progress_path"
        fi
        echo "Created $progress_path"
    else
        echo "$progress_path already exists, skipping"
    fi
}

if [ "$SLUG_MODE" -eq 1 ]; then
    SLUG="$(slugify "$PROJECT_NAME")"
    if [ -z "$SLUG" ]; then
        SLUG="untitled-$(short_uuid)"
    fi
    BASE_ID="${DATE}-${SLUG}"
    PLAN_ID="$BASE_ID"
    PLAN_ROOT="${PWD}/.planning"
    PLAN_CONTAINER="${PLAN_ROOT}/plans"
    counter=2
    while [ -d "${PLAN_CONTAINER}/${PLAN_ID}" ]; do
        PLAN_ID="${BASE_ID}-${counter}"
        counter=$((counter + 1))
    done
    PLAN_DIR="${PLAN_CONTAINER}/${PLAN_ID}"
    mkdir -p "$PLAN_DIR"

    echo "Initializing planning files for: ${PROJECT_NAME:-untitled} (template: $TEMPLATE)"
    echo "PLAN_ID=$PLAN_ID"
    create_files_in "$PLAN_DIR"
    write_metadata "$PLAN_DIR" "$PLAN_ID" "${PROJECT_NAME:-untitled}"
    printf "%s\n" "$PLAN_ID" > "${PLAN_ROOT}/.active_plan"
    attach_session "$ATTACH_SESSION_ID" "$PLAN_ID" "$PLAN_DIR"
    echo ""
    echo "Active plan recorded: ${PLAN_ROOT}/.active_plan"
    if [ -n "$ATTACH_SESSION_ID" ]; then
        echo "Session attached: ${PLAN_ROOT}/sessions/${ATTACH_SESSION_ID}.json"
    fi
    echo "Pin this terminal to the plan for parallel sessions:"
    echo "  export PLAN_ID=$PLAN_ID"
else
    PROJECT_NAME="${PROJECT_NAME:-project}"
    echo "Initializing planning files for: $PROJECT_NAME (template: $TEMPLATE)"
    create_files_in "$(pwd)"
    echo ""
    echo "Planning files initialized!"
    echo "Files: task_plan.md, findings.md, progress.md"
fi
