from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HOOK_DIR = Path(__file__).resolve().parents[1]
ADAPTER_PATH = HOOK_DIR / "codex_hook_adapter.py"
SESSION_CATCHUP_PATH = (
    Path.home() / ".codex" / "skills" / "planning-with-files" / "scripts" / "session-catchup.py"
)

spec = importlib.util.spec_from_file_location("codex_hook_adapter", ADAPTER_PATH)
assert spec is not None and spec.loader is not None
adapter = importlib.util.module_from_spec(spec)
sys.modules["codex_hook_adapter"] = adapter
spec.loader.exec_module(adapter)

catchup_spec = importlib.util.spec_from_file_location("session_catchup", SESSION_CATCHUP_PATH)
assert catchup_spec is not None and catchup_spec.loader is not None
session_catchup = importlib.util.module_from_spec(catchup_spec)
sys.modules["session_catchup"] = session_catchup
catchup_spec.loader.exec_module(session_catchup)


class AdapterPlanningTests(unittest.TestCase):
    def test_unopted_subagent_is_skipped(self) -> None:
        payload = {
            "subagent": {"role": "worker"},
            "session_id": "child-session",
        }
        self.assertTrue(adapter.is_subagent_payload(payload))
        self.assertTrue(adapter.should_skip_planning_for_subagent(payload))

    def test_real_spawn_prompt_can_opt_subagent_in(self) -> None:
        payload = {
            "id": "child-thread",
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "parent-thread",
                        "agent_nickname": "Laplace",
                        "agent_role": "worker",
                    }
                }
            },
            "prompt": "Use the planning-with-files workflow for this subtask.",
        }
        self.assertTrue(adapter.is_subagent_payload(payload))
        self.assertFalse(adapter.should_skip_planning_for_subagent(payload))
        self.assertEqual(adapter.session_key_from_payload(payload), "child-thread")
        self.assertEqual(adapter.parent_session_key_from_payload(payload), "parent-thread")
        self.assertEqual(adapter.subagent_role_from_payload(payload), "worker")
        self.assertEqual(adapter.subagent_name_from_payload(payload), "Laplace")

    def test_opted_subagent_uses_session_scoped_plan_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "subagent": {"role": "worker"},
                "session_id": "child/session:123",
                "metadata": {"active_skills": ["planning-with-files"]},
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertFalse(adapter.should_skip_planning_for_subagent(payload))
                self.assertEqual(
                    adapter.planning_dir_from_payload(payload, cwd),
                    cwd / ".codex" / "planning" / "child-session-123",
                )

    def test_plan_id_takes_shared_long_running_plan_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "subagent": {"role": "worker"},
                "session_id": "child-session",
                "plan_id": "shared/path:task",
                "planning_with_files": True,
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    adapter.planning_dir_from_payload(payload, cwd),
                    cwd / ".planning" / "plans" / "shared-path-task",
                )

    def test_session_json_mapping_points_to_plan_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "2026-05-03-task-a"
            plan_dir.mkdir(parents=True)
            (plan_dir / "task_plan.md").write_text(
                "# Task Plan\n\n### Phase 1\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            sessions_dir = cwd / ".planning" / "sessions"
            sessions_dir.mkdir(parents=True)
            (sessions_dir / "session-1.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "session_id": "session-1",
                        "plan_id": "2026-05-03-task-a",
                        "mode": "attached",
                    }
                ),
                encoding="utf-8",
            )

            payload = {"session_id": "session-1"}
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertTrue(adapter.session_is_attached(payload, cwd))
                self.assertEqual(adapter.planning_dir_from_payload(payload, cwd), plan_dir)

    def test_session_attachment_gate_blocks_unattached_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            (cwd / ".planning" / "sessions").mkdir(parents=True)
            payload = {"session_id": "unattached"}
            self.assertFalse(adapter.session_is_attached(payload, cwd))

    def test_parent_plan_dir_prefers_parent_plan_id_then_parent_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(
                    adapter.parent_planning_dir_from_payload(
                        {"parent_plan_id": "parent-task"}, cwd
                    ),
                    cwd / ".planning" / "plans" / "parent-task",
                )
                self.assertEqual(
                    adapter.parent_planning_dir_from_payload(
                        {"parent_session_id": "parent/session"}, cwd
                    ),
                    cwd / ".codex" / "planning" / "parent-session",
                )

    def test_record_subagent_planning_index_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "subagent": {
                    "role": "worker",
                    "name": "Worker A",
                    "task": "inspect adapter behavior",
                },
                "session_id": "child-session",
                "parent_session_id": "parent-session",
                "metadata": {"planning_with_files": True},
            }
            with mock.patch.dict(os.environ, {}, clear=True):
                first = adapter.record_subagent_planning_index(payload, cwd, "SessionStart")
                second = adapter.record_subagent_planning_index(payload, cwd, "PreToolUse")

            self.assertEqual(first, second)
            assert first is not None
            jsonl_file = first.with_name("subagents.jsonl")
            jsonl_lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(jsonl_lines), 2)
            events = [json.loads(line) for line in jsonl_lines]
            self.assertEqual(events[0]["child_key"], "child-session")
            self.assertEqual(events[0]["parent_key"], "parent-session")
            self.assertEqual(events[1]["hook_name"], "PreToolUse")

            text = first.read_text(encoding="utf-8")
            self.assertEqual(text.count("| child-session |"), 1)
            self.assertIn("| parent-session |", text)
            self.assertIn("| worker |", text)
            self.assertIn("| Worker A |", text)
            self.assertIn("| inspect adapter behavior |", text)
            self.assertIn(str(cwd / ".codex" / "planning" / "child-session"), text)
            self.assertIn("| PreToolUse |", text)

    def test_record_subagent_planning_index_requires_opt_in_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertIsNone(
                    adapter.record_subagent_planning_index(
                        {"subagent": {}, "session_id": "child", "parent_session_id": "parent"},
                        cwd,
                        "SessionStart",
                    )
                )
                self.assertIsNone(
                    adapter.record_subagent_planning_index(
                        {"subagent": {}, "session_id": "child", "planning_with_files": True},
                        cwd,
                        "SessionStart",
                    )
                )
            self.assertFalse((cwd / ".codex" / "planning" / "parent" / "subagents.md").exists())
            self.assertFalse((cwd / ".codex" / "planning" / "parent" / "subagents.jsonl").exists())

    def test_real_spawn_source_payload_registers_parent_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "id": "child-thread",
                "source": {
                    "subagent": {
                        "thread_spawn": {
                            "parent_thread_id": "parent-thread",
                            "agent_nickname": "Laplace",
                            "agent_role": "worker",
                        }
                    }
                },
                "prompt": "Use the planning-with-files workflow for this subtask.",
            }

            with mock.patch.dict(os.environ, {}, clear=True):
                index = adapter.record_subagent_planning_index(payload, cwd, "UserPromptSubmit")

            assert index is not None
            self.assertEqual(index.parent, cwd / ".codex" / "planning" / "parent-thread")
            events = [
                json.loads(line)
                for line in index.with_name("subagents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(events[0]["child_key"], "child-thread")
            self.assertEqual(events[0]["parent_key"], "parent-thread")
            self.assertEqual(events[0]["role"], "worker")
            self.assertEqual(events[0]["name"], "Laplace")
            self.assertIn("| child-thread | parent-thread | worker | Laplace |", index.read_text(encoding="utf-8"))

    def test_nested_subagents_register_under_direct_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            child_payload = {
                "subagent": {"role": "worker", "task": "child task"},
                "session_id": "child-session",
                "parent_session_id": "root-session",
                "planning_with_files": True,
            }
            grandchild_payload = {
                "subagent": {"role": "worker", "task": "grandchild task"},
                "session_id": "grandchild-session",
                "parent_session_id": "child-session",
                "planning_with_files": True,
            }

            with mock.patch.dict(os.environ, {}, clear=True):
                root_index = adapter.record_subagent_planning_index(child_payload, cwd, "SessionStart")
                child_index = adapter.record_subagent_planning_index(
                    grandchild_payload, cwd, "SessionStart"
                )

            assert root_index is not None
            assert child_index is not None
            self.assertEqual(root_index.parent, cwd / ".codex" / "planning" / "root-session")
            self.assertEqual(child_index.parent, cwd / ".codex" / "planning" / "child-session")

            root_events = [
                json.loads(line)
                for line in root_index.with_name("subagents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            child_events = [
                json.loads(line)
                for line in child_index.with_name("subagents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([event["child_key"] for event in root_events], ["child-session"])
            self.assertEqual([event["child_key"] for event in child_events], ["grandchild-session"])
            self.assertIn("| grandchild-session | child-session |", child_index.read_text(encoding="utf-8"))

    def test_markdown_is_regenerated_from_jsonl_latest_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            parent_dir = Path(tmp)
            (parent_dir / "subagents.jsonl").write_text(
                "\n".join(
                    [
                        "not-json",
                        json.dumps(
                            {
                                "schema_version": 1,
                                "event": "subagent_seen",
                                "timestamp_utc": "2026-04-27T00:00:00+00:00",
                                "hook_name": "SessionStart",
                                "child_key": "child",
                                "parent_key": "parent",
                                "role": "worker",
                                "name": "old",
                                "task": "first",
                                "plan_dir": "/tmp/child",
                                "plan_id": "",
                            }
                        ),
                        json.dumps(
                            {
                                "schema_version": 1,
                                "event": "subagent_seen",
                                "timestamp_utc": "2026-04-27T00:01:00+00:00",
                                "hook_name": "Stop",
                                "child_key": "child",
                                "parent_key": "parent",
                                "role": "worker",
                                "name": "new",
                                "task": "second",
                                "plan_dir": "/tmp/child",
                                "plan_id": "",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            markdown = adapter.render_subagent_markdown_from_jsonl(parent_dir)
            text = markdown.read_text(encoding="utf-8")
            self.assertEqual(text.count("| child |"), 1)
            self.assertIn("| child | parent | worker | new | second |", text)
            self.assertNotIn("| child | parent | worker | old | first |", text)

    def test_parallel_subagent_event_writes_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            script = f"""
import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("codex_hook_adapter", {str(ADAPTER_PATH)!r})
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
payload = json.loads(sys.argv[1])
adapter.record_subagent_planning_index(payload, Path(sys.argv[2]), "Parallel")
"""
            processes = []
            for index in range(8):
                payload = {
                    "subagent": {"role": "worker", "task": f"parallel {index}"},
                    "session_id": f"child-{index}",
                    "parent_session_id": "parent-session",
                    "planning_with_files": True,
                }
                processes.append(
                    subprocess.Popen(
                        [sys.executable, "-c", script, json.dumps(payload), str(cwd)],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                )

            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)

            parent_dir = cwd / ".codex" / "planning" / "parent-session"
            events = [
                json.loads(line)
                for line in (parent_dir / "subagents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            child_keys = {event["child_key"] for event in events}
            self.assertEqual(child_keys, {f"child-{index}" for index in range(8)})
            text = (parent_dir / "subagents.md").read_text(encoding="utf-8")
            for index in range(8):
                self.assertIn(f"| child-{index} | parent-session |", text)

    def test_parent_hook_can_register_real_subagent_session_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp) / "project"
            cwd.mkdir()
            sessions_dir = Path(tmp) / "sessions"
            session_dir = sessions_dir / "2026" / "04" / "27"
            session_dir.mkdir(parents=True)
            session_file = session_dir / "rollout-2026-04-27T19-46-27-child-thread.jsonl"
            child_plan_dir = cwd / ".codex" / "planning" / "real-child-plan"
            session_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "session_meta",
                                "payload": {
                                    "id": "child-thread",
                                    "cwd": str(cwd),
                                    "source": {
                                        "subagent": {
                                            "thread_spawn": {
                                                "parent_thread_id": "parent-thread",
                                                "depth": 1,
                                                "agent_nickname": "Raman",
                                                "agent_role": "worker",
                                            }
                                        }
                                    },
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "event_msg",
                                "payload": {
                                    "type": "user_message",
                                    "message": (
                                        "Use the planning-with-files workflow. "
                                        f"Write under {child_plan_dir}/ only."
                                    ),
                                },
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            payload = {"cwd": str(cwd), "session_id": "parent-thread"}
            with mock.patch.dict(os.environ, {"CODEX_SESSIONS_DIR": str(sessions_dir)}, clear=True):
                recorded = adapter.record_spawned_subagents_from_session_logs(
                    payload, cwd, "UserPromptSubmit"
                )
                recorded_again = adapter.record_spawned_subagents_from_session_logs(
                    payload, cwd, "UserPromptSubmit"
                )

            self.assertEqual(len(recorded), 1)
            self.assertEqual(len(recorded_again), 1)
            parent_dir = cwd / ".codex" / "planning" / "parent-thread"
            events = [
                json.loads(line)
                for line in (parent_dir / "subagents.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["child_key"], "child-thread")
            self.assertEqual(events[0]["parent_key"], "parent-thread")
            self.assertEqual(events[0]["role"], "worker")
            self.assertEqual(events[0]["name"], "Raman")
            self.assertEqual(events[0]["plan_dir"], str(child_plan_dir))
            text = (parent_dir / "subagents.md").read_text(encoding="utf-8")
            self.assertIn("| child-thread | parent-thread | worker | Raman |", text)


class HookWrapperTests(unittest.TestCase):
    def _run_hook(self, hook_name: str, payload: dict[str, object], cwd: Path) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("CODEX_PLAN_DIR", None)
        env.pop("PLAN_ID", None)
        env.pop("CODEX_PLAN_ID", None)
        env.pop("CODEX_TASK_ID", None)
        return subprocess.run(
            [sys.executable, str(HOOK_DIR / hook_name)],
            input=json.dumps(payload),
            cwd=str(cwd),
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )

    def _system_message(self, result: subprocess.CompletedProcess[str]) -> str:
        payload = json.loads(result.stdout)
        message = payload.get("systemMessage")
        self.assertIsInstance(message, str)
        return message

    def test_user_prompt_submit_registers_opted_subagent_and_reads_child_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            child_plan_dir = cwd / ".codex" / "planning" / "child-session"
            child_plan_dir.mkdir(parents=True)
            (child_plan_dir / "task_plan.md").write_text(
                "# Task Plan: Child\n\n### Phase 1\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            (child_plan_dir / "progress.md").write_text(
                "# Progress\nchild progress\n",
                encoding="utf-8",
            )
            (child_plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")

            payload = {
                "cwd": str(cwd),
                "subagent": {"role": "worker", "task": "build child plan"},
                "session_id": "child-session",
                "parent_session_id": "parent-session",
                "metadata": {"planning_with_files": True},
            }
            result = self._run_hook("user_prompt_submit.py", payload, cwd)

            self.assertEqual(result.returncode, 0, result.stderr)
            message = self._system_message(result)
            self.assertIn("ACTIVE PLAN", message)
            self.assertIn(str(child_plan_dir), message)

            parent_index = cwd / ".codex" / "planning" / "parent-session" / "subagents.md"
            self.assertTrue(parent_index.exists())
            parent_events = parent_index.with_name("subagents.jsonl")
            self.assertTrue(parent_events.exists())
            events = [json.loads(line) for line in parent_events.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(events[0]["child_key"], "child-session")
            self.assertEqual(events[0]["parent_key"], "parent-session")
            text = parent_index.read_text(encoding="utf-8")
            self.assertIn("| child-session |", text)
            self.assertIn("| parent-session |", text)
            self.assertIn("| worker |", text)
            self.assertIn("| build child plan |", text)

    def test_all_hook_wrappers_register_opted_subagent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            child_plan_dir = cwd / ".codex" / "planning" / "child-session"
            child_plan_dir.mkdir(parents=True)
            (child_plan_dir / "task_plan.md").write_text(
                "# Task Plan: Child\n\n### Phase 1\n- **Status:** complete\n",
                encoding="utf-8",
            )
            (child_plan_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
            (child_plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")

            payload = {
                "cwd": str(cwd),
                "subagent": {"role": "worker", "task": "exercise all hooks"},
                "session_id": "child-session",
                "parent_session_id": "parent-session",
                "metadata": {"planning_with_files": True},
            }
            hooks = [
                "session_start.py",
                "user_prompt_submit.py",
                "pre_tool_use.py",
                "post_tool_use.py",
                "stop.py",
            ]
            for hook in hooks:
                result = self._run_hook(hook, payload, cwd)
                self.assertEqual(result.returncode, 0, f"{hook}: {result.stderr}")

            parent_index = cwd / ".codex" / "planning" / "parent-session" / "subagents.md"
            parent_events = parent_index.with_name("subagents.jsonl")
            self.assertTrue(parent_index.exists())
            self.assertTrue(parent_events.exists())
            events = [json.loads(line) for line in parent_events.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([event["hook_name"] for event in events], [
                "SessionStart",
                "UserPromptSubmit",
                "PreToolUse",
                "PostToolUse",
                "Stop",
            ])
            text = parent_index.read_text(encoding="utf-8")
            self.assertEqual(text.count("| child-session | parent-session |"), 1)
            self.assertIn("| Stop |", text)

    def test_stop_hook_skips_unopted_subagent_without_parent_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            payload = {
                "cwd": str(cwd),
                "subagent": {"role": "worker"},
                "session_id": "child-session",
                "parent_session_id": "parent-session",
            }
            result = self._run_hook("stop.py", payload, cwd)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(
                (cwd / ".codex" / "planning" / "parent-session" / "subagents.md").exists()
            )
            self.assertFalse(
                (cwd / ".codex" / "planning" / "parent-session" / "subagents.jsonl").exists()
            )

    def test_unattached_parent_session_is_silent_when_session_gate_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "task-a"
            plan_dir.mkdir(parents=True)
            (plan_dir / "task_plan.md").write_text(
                "# Task Plan\n\n### Phase 1\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            (plan_dir / "progress.md").write_text("# Progress\n", encoding="utf-8")
            (cwd / ".planning" / "sessions").mkdir(parents=True)

            result = self._run_hook("user_prompt_submit.py", {"cwd": str(cwd), "session_id": "s1"}, cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")

    def test_attached_parent_session_reads_mapped_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "task-a"
            plan_dir.mkdir(parents=True)
            (plan_dir / "task_plan.md").write_text(
                "# Task Plan: A\n\n### Phase 1\n- **Status:** in_progress\n",
                encoding="utf-8",
            )
            (plan_dir / "progress.md").write_text("# Progress\nmapped progress\n", encoding="utf-8")
            sessions_dir = cwd / ".planning" / "sessions"
            sessions_dir.mkdir(parents=True)
            (sessions_dir / "s1.json").write_text(
                json.dumps({"session_id": "s1", "plan_id": "task-a"}),
                encoding="utf-8",
            )

            result = self._run_hook("user_prompt_submit.py", {"cwd": str(cwd), "session_id": "s1"}, cwd)
            self.assertEqual(result.returncode, 0, result.stderr)
            message = self._system_message(result)
            self.assertIn("Task Plan: A", message)
            self.assertIn("mapped progress", message)


class SessionCatchupTests(unittest.TestCase):
    def test_session_catchup_uses_codex_plan_dir_for_planning_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with mock.patch.dict(os.environ, {}, clear=True):
                self.assertEqual(session_catchup.planning_root_from_env(str(project)), project)

            with mock.patch.dict(os.environ, {"CODEX_PLAN_DIR": ".codex/planning/child"}, clear=True):
                self.assertEqual(
                    session_catchup.planning_root_from_env(str(project)),
                    project / ".codex" / "planning" / "child",
                )

            absolute = project / "absolute-plan"
            with mock.patch.dict(os.environ, {"CODEX_PLAN_DIR": str(absolute)}, clear=True):
                self.assertEqual(session_catchup.planning_root_from_env(str(project)), absolute)


if __name__ == "__main__":
    unittest.main()
