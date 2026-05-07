#!/bin/sh
# Audit the local Codex overlay against the latest upstream planning-with-files release.

set -eu

RUN_CLI=0
if [ "${1:-}" = "--cli" ]; then
  RUN_CLI=1
  shift
fi

if [ "$#" -gt 1 ]; then
  echo "usage: $0 [--cli] [base-tag]" >&2
  exit 2
fi

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

BASE_TAG="${1:-}"
if [ -z "$BASE_TAG" ]; then
  BASE_TAG="$(git tag -l 'v*' --sort=-v:refname | head -n 1)"
fi

if [ -z "$BASE_TAG" ]; then
  echo "No v* tag found. Fetch upstream tags first." >&2
  exit 1
fi

echo "== Local Codex overlay audit =="
echo "repo: $REPO_ROOT"
echo "base: $BASE_TAG"
echo "head: $(git rev-parse --short HEAD)"
echo

echo "== Local commits after $BASE_TAG =="
git log --oneline "$BASE_TAG..HEAD" || true
echo

echo "== Files changed by local overlay =="
git diff --name-only "$BASE_TAG..HEAD" | sed 's/^/- /'
echo

echo "== Non-Codex/shared files to review =="
git diff --name-only "$BASE_TAG..HEAD" |
  grep -Ev '^(\.codex/|commands/plan-attest\.md$|\.gitignore$|docs/local-codex-overlay\.md$|scripts/audit-local-codex-overlay\.sh$)' |
  sed 's/^/- /' || true
echo

echo "== Python hook unit tests =="
python3 -m unittest discover -s .codex/hooks/tests -p 'test*.py'
echo

echo "== Python compile check =="
python3 -m py_compile \
  .codex/hooks/codex_hook_adapter.py \
  .codex/hooks/user_prompt_submit.py \
  .codex/hooks/pre_tool_use.py \
  .codex/hooks/post_tool_use.py \
  .codex/hooks/stop.py \
  .codex/hooks/session_start.py \
  .codex/hooks/tests/test_codex_hook_adapter.py \
  .codex/hooks/tests/test_planning_runtime_regressions.py
echo

echo "== UserPromptSubmit JSON smoke =="
TMPDIR="${TMPDIR:-/tmp}"
fixture="$(mktemp -d "$TMPDIR/pwf-overlay-audit.XXXXXX")"
mkdir -p "$fixture/.planning/plans/audit"
cat > "$fixture/.planning/plans/audit/task_plan.md" <<'PLAN'
# Task Plan: Overlay Audit

### Phase 1
**Status:** complete
PLAN
printf '# Progress\naudit\n' > "$fixture/.planning/plans/audit/progress.md"
printf '# Findings\n' > "$fixture/.planning/plans/audit/findings.md"
printf 'audit\n' > "$fixture/.planning/.active_plan"
printf '{"cwd":"%s"}' "$fixture" |
  python3 .codex/hooks/user_prompt_submit.py > "$fixture/user-prompt.out"
python3 -m json.tool "$fixture/user-prompt.out" >/dev/null
python3 - "$fixture/user-prompt.out" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
message = payload.get("systemMessage")
if not isinstance(message, str) or "Overlay Audit" not in message:
    raise SystemExit("UserPromptSubmit output missing systemMessage plan context")
PY
echo "UserPromptSubmit JSON OK"
echo

if [ "$RUN_CLI" -eq 1 ]; then
  echo "== Real Codex CLI smoke =="
  cli_dir="$(mktemp -d "$TMPDIR/pwf-overlay-cli.XXXXXX")"
  cat > "$cli_dir/task_plan.md" <<'PLAN'
# Task Plan: Codex CLI Smoke

### Phase 1
**Status:** complete
PLAN
  printf '# Progress\ncli smoke\n' > "$cli_dir/progress.md"
  printf '# Findings\n' > "$cli_dir/findings.md"
  CODEX_CLI_RUST_LOG=error codex exec \
    --ephemeral \
    --skip-git-repo-check \
    --json \
    --color never \
    -C "$cli_dir" \
    -m gpt-5.4-mini \
    -c model_reasoning_effort=low \
    "Reply exactly OK. Do not use tools." \
    > "$cli_dir/stdout.jsonl" \
    2> "$cli_dir/stderr.log" </dev/null
  if grep -E "hook|UserPromptSubmit|invalid|failed|ERROR|WARN" "$cli_dir/stderr.log" >/dev/null 2>&1; then
    echo "Codex CLI stderr contained hook/error text:" >&2
    cat "$cli_dir/stderr.log" >&2
    exit 1
  fi
  echo "Codex CLI smoke OK"
  echo
fi

echo "Overlay audit complete."
