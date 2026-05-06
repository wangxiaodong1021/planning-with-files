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

    adapter.record_spawned_subagents_from_session_logs(payload, root, "SessionStart")
    adapter.record_subagent_planning_index(payload, root, "SessionStart")
    stdout, _ = adapter.run_shell_script("user-prompt-submit.sh", root, adapter.hook_env(payload, root))
    if stdout:
        adapter.emit_json({"systemMessage": stdout})


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
