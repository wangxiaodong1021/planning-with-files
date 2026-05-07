#!/usr/bin/env python3
from __future__ import annotations

import local_codex_overlay as adapter


def main() -> None:
    payload = adapter.load_payload()
    if adapter.should_skip_planning_for_subagent(payload):
        return

    root = adapter.cwd_from_payload(payload)
    if not adapter.is_subagent_payload(payload) and not adapter.session_is_attached(payload, root):
        return

    adapter.record_subagent_planning_index(payload, root, "PreToolUse")
    stdout, stderr = adapter.run_shell_script("pre-tool-use.sh", root, adapter.hook_env(payload, root))

    result = adapter.parse_json(stdout)
    decision = result.get("decision")
    if decision and decision != "allow":
        adapter.emit_json(result)
        return

    if "PLAN TAMPERED" in stderr:
        adapter.emit_json({"systemMessage": stderr})
        return


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
