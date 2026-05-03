#!/usr/bin/env python3
from __future__ import annotations

import codex_hook_adapter as adapter


def main() -> None:
    payload = adapter.load_payload()
    if adapter.should_skip_planning_for_subagent(payload):
        return

    root = adapter.cwd_from_payload(payload)
    if not adapter.is_subagent_payload(payload) and not adapter.session_is_attached(payload, root):
        return

    adapter.record_spawned_subagents_from_session_logs(payload, root, "Stop")
    adapter.record_subagent_planning_index(payload, root, "Stop")
    stdout, _ = adapter.run_shell_script("stop.sh", root, adapter.hook_env(payload, root))
    result = adapter.parse_json(stdout)

    message = result.get("followup_message")
    if not isinstance(message, str) or not message:
        return

    if "ALL PHASES COMPLETE" in message:
        adapter.emit_json({"systemMessage": message})
        return

    if bool(payload.get("stop_hook_active")):
        adapter.emit_json({"systemMessage": message})
        return

    adapter.emit_json({"decision": "block", "reason": message})


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
