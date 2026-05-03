"""Regression tests for local Codex subagent planning support.

The upstream v2.36 session isolation model is plan-scoped. These tests ensure
that subagent support remains an opt-in extension and does not regress while
normal parent sessions use .planning/plans/<plan-id>/ mappings.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / ".codex" / "hooks" / "codex_hook_adapter.py"

spec = importlib.util.spec_from_file_location("codex_hook_adapter", ADAPTER_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
sys.modules["codex_hook_adapter"] = adapter
spec.loader.exec_module(adapter)


class CodexSubagentPlanningTests(unittest.TestCase):
    def test_unopted_subagent_is_skipped(self) -> None:
        payload = {"subagent": {"role": "worker"}, "session_id": "child-session"}
        self.assertTrue(adapter.is_subagent_payload(payload))
        self.assertTrue(adapter.should_skip_planning_for_subagent(payload))

    def test_opted_subagent_uses_session_scoped_plan_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "subagent": {"role": "worker"},
                "session_id": "child/session:123",
                "metadata": {"active_skills": ["planning-with-files"]},
            }
            with mock.patch.dict("os.environ", {}, clear=True):
                self.assertFalse(adapter.should_skip_planning_for_subagent(payload))
                self.assertEqual(
                    adapter.planning_dir_from_payload(payload, cwd),
                    cwd / ".codex" / "planning" / "child-session-123",
                )

    def test_parent_plan_id_uses_plan_scoped_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            with mock.patch.dict("os.environ", {}, clear=True):
                self.assertEqual(
                    adapter.parent_planning_dir_from_payload({"parent_plan_id": "task-a"}, cwd),
                    cwd / ".planning" / "plans" / "task-a",
                )

    def test_record_subagent_planning_index_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "subagent": {"role": "worker", "name": "Worker A", "task": "inspect behavior"},
                "session_id": "child-session",
                "parent_session_id": "parent-session",
                "metadata": {"planning_with_files": True},
            }
            with mock.patch.dict("os.environ", {}, clear=True):
                first = adapter.record_subagent_planning_index(payload, cwd, "SessionStart")
                second = adapter.record_subagent_planning_index(payload, cwd, "Stop")

            self.assertEqual(first, second)
            assert first is not None
            jsonl = first.with_name("subagents.jsonl")
            events = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([event["hook_name"] for event in events], ["SessionStart", "Stop"])
            text = first.read_text(encoding="utf-8")
            self.assertEqual(text.count("| child-session | parent-session |"), 1)
            self.assertIn("| Stop |", text)


if __name__ == "__main__":
    unittest.main()
