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

    adapter.record_subagent_planning_index(payload, root, "PostToolUse")


if __name__ == "__main__":
    raise SystemExit(adapter.main_guard(main))
