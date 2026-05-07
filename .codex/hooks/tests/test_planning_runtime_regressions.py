from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HOOK_DIR = Path(__file__).resolve().parents[1]
CODEX_HOME = HOOK_DIR.parent
SKILL_DIR = CODEX_HOME / "skills" / "planning-with-files"
SCRIPT_DIR = SKILL_DIR / "scripts"


def run_cmd(
    args: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    merged_env.pop("CODEX_PLAN_DIR", None)
    merged_env.pop("PLAN_ID", None)
    merged_env.pop("CODEX_PLAN_ID", None)
    merged_env.pop("CODEX_TASK_ID", None)
    if env:
        merged_env.update(env)
    return subprocess.run(
        args,
        cwd=str(cwd),
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )


def write_plan(plan_dir: Path, title: str = "Task Plan") -> None:
    plan_dir.mkdir(parents=True, exist_ok=True)
    (plan_dir / "task_plan.md").write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                "### Phase 1: Done",
                "**Status:** complete",
                "",
                "### Phase 2: Todo",
                "**Status:** pending",
                "",
                "Example prose: ### Phase should not be counted.",
                "Example prose: **Status:** complete should not be counted.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (plan_dir / "progress.md").write_text("# Progress\nruntime progress\n", encoding="utf-8")
    (plan_dir / "findings.md").write_text("# Findings\n", encoding="utf-8")


def system_message_from(result: subprocess.CompletedProcess[str]) -> str:
    payload = json.loads(result.stdout)
    message = payload.get("systemMessage")
    if not isinstance(message, str):
        raise AssertionError(f"expected systemMessage in hook JSON, got: {result.stdout!r}")
    return message


class PlanningRuntimeRegressionTests(unittest.TestCase):
    def test_resolvers_keep_codex_plan_dir_and_plans_container_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            active_plan = cwd / ".planning" / "plans" / "alpha"
            custom_plan = cwd / "custom-plan"
            write_plan(active_plan, "Task Plan: Alpha")
            write_plan(custom_plan, "Task Plan: Custom")
            (cwd / ".planning" / ".active_plan").write_text("alpha", encoding="utf-8")

            for resolver in (
                SCRIPT_DIR / "resolve-plan-dir.sh",
                HOOK_DIR / "resolve-plan-dir.sh",
            ):
                active = run_cmd(["sh", str(resolver)], cwd)
                self.assertEqual(active.returncode, 0, active.stderr)
                self.assertEqual(Path(active.stdout.strip()).resolve(), active_plan.resolve())

                override = run_cmd(
                    ["sh", str(resolver)],
                    cwd,
                    env={"CODEX_PLAN_DIR": str(custom_plan)},
                )
                self.assertEqual(override.returncode, 0, override.stderr)
                self.assertEqual(Path(override.stdout.strip()).resolve(), custom_plan.resolve())

    def test_check_complete_and_stop_ignore_prose_and_support_inline_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan = cwd / "task_plan.md"
            plan.write_text(
                "\n".join(
                    [
                        "# Plan",
                        "",
                        "### Phase 1: Done",
                        "**Status:** complete",
                        "",
                        "### Phase 2: Todo",
                        "**Status:** pending",
                        "",
                        "Example prose: ### Phase fake",
                        "Example prose: **Status:** complete",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            checker = run_cmd(["sh", str(SCRIPT_DIR / "check-complete.sh"), str(plan)], cwd)
            self.assertEqual(checker.returncode, 0, checker.stderr)
            self.assertIn("1/2 phases complete", checker.stdout)

            stop = run_cmd(["sh", str(HOOK_DIR / "stop.sh")], cwd)
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertIn("1/2 phases done", stop.stdout)

            plan.write_text(
                "\n".join(
                    [
                        "# Inline Plan",
                        "",
                        "- [complete] old format done",
                        "- [pending] old format todo",
                        "Example prose [complete] should not count",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            inline_checker = run_cmd(["sh", str(SCRIPT_DIR / "check-complete.sh"), str(plan)], cwd)
            self.assertEqual(inline_checker.returncode, 0, inline_checker.stderr)
            self.assertIn("1/2 phases complete", inline_checker.stdout)

            inline_stop = run_cmd(["sh", str(HOOK_DIR / "stop.sh")], cwd)
            self.assertEqual(inline_stop.returncode, 0, inline_stop.stderr)
            self.assertIn("1/2 phases done", inline_stop.stdout)

    def test_plan_attestation_blocks_tampered_user_prompt_and_pretool_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "alpha"
            write_plan(plan_dir, "Task Plan: Alpha")
            (cwd / ".planning" / ".active_plan").write_text("alpha", encoding="utf-8")

            attest = run_cmd(["sh", str(SCRIPT_DIR / "attest-plan.sh")], cwd)
            self.assertEqual(attest.returncode, 0, attest.stderr)
            self.assertTrue((plan_dir / ".attestation").exists())

            user_prompt_ok = run_cmd(
                [sys.executable, str(HOOK_DIR / "user_prompt_submit.py")],
                cwd,
                stdin=json.dumps({"cwd": str(cwd)}),
            )
            self.assertEqual(user_prompt_ok.returncode, 0, user_prompt_ok.stderr)
            ok_message = system_message_from(user_prompt_ok)
            self.assertIn("Plan-SHA256:", ok_message)
            self.assertIn("Task Plan: Alpha", ok_message)

            with (plan_dir / "task_plan.md").open("a", encoding="utf-8") as handle:
                handle.write("\nTampered after attestation.\n")

            user_prompt = run_cmd(
                [sys.executable, str(HOOK_DIR / "user_prompt_submit.py")],
                cwd,
                stdin=json.dumps({"cwd": str(cwd)}),
            )
            self.assertEqual(user_prompt.returncode, 0, user_prompt.stderr)
            tamper_message = system_message_from(user_prompt)
            self.assertIn("PLAN TAMPERED", tamper_message)
            self.assertNotIn("---BEGIN PLAN DATA---", tamper_message)

            pretool = run_cmd(
                [sys.executable, str(HOOK_DIR / "pre_tool_use.py")],
                cwd,
                stdin=json.dumps({"cwd": str(cwd)}),
            )
            self.assertEqual(pretool.returncode, 0, pretool.stderr)
            self.assertIn("PLAN TAMPERED", pretool.stdout)

    def test_attestation_clear_reopens_injection_without_tamper_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "beta"
            write_plan(plan_dir, "Task Plan: Beta")
            (cwd / ".planning" / ".active_plan").write_text("beta", encoding="utf-8")

            attest = run_cmd(["sh", str(SCRIPT_DIR / "attest-plan.sh")], cwd)
            self.assertEqual(attest.returncode, 0, attest.stderr)

            show = run_cmd(["sh", str(SCRIPT_DIR / "attest-plan.sh"), "--show"], cwd)
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertIn("SHA-256:", show.stdout)

            clear = run_cmd(["sh", str(SCRIPT_DIR / "attest-plan.sh"), "--clear"], cwd)
            self.assertEqual(clear.returncode, 0, clear.stderr)
            self.assertFalse((plan_dir / ".attestation").exists())

            user_prompt = run_cmd(
                [sys.executable, str(HOOK_DIR / "user_prompt_submit.py")],
                cwd,
                stdin=json.dumps({"cwd": str(cwd)}),
            )
            self.assertEqual(user_prompt.returncode, 0, user_prompt.stderr)
            message = system_message_from(user_prompt)
            self.assertIn("Task Plan: Beta", message)
            self.assertNotIn("PLAN TAMPERED", message)

    def test_json_session_mapping_with_plan_dir_surfaces_plan_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            plan_dir = cwd / ".planning" / "plans" / "mapped"
            write_plan(plan_dir, "Task Plan: Mapped")
            sessions_dir = cwd / ".planning" / "sessions"
            sessions_dir.mkdir(parents=True)
            (sessions_dir / "session-1.json").write_text(
                json.dumps(
                    {
                        "session_id": "session-1",
                        "plan_id": "mapped",
                        "plan_dir": str(plan_dir),
                        "mode": "attached",
                    }
                ),
                encoding="utf-8",
            )

            result = run_cmd(
                [sys.executable, str(HOOK_DIR / "user_prompt_submit.py")],
                cwd,
                stdin=json.dumps({"cwd": str(cwd), "session_id": "session-1"}),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            message = system_message_from(result)
            self.assertIn("Task Plan: Mapped", message)
            self.assertIn(str(plan_dir), message)

    def test_static_powershell_mirrors_keep_local_resolution_and_anchored_counting(self) -> None:
        resolver = (SCRIPT_DIR / "resolve-plan-dir.ps1").read_text(encoding="utf-8")
        checker = (SCRIPT_DIR / "check-complete.ps1").read_text(encoding="utf-8")

        self.assertIn("CODEX_PLAN_DIR", resolver)
        self.assertIn("$planContainer", resolver)
        self.assertIn("task_plan.md", resolver)
        self.assertIn("RegexOptions]::Multiline", checker)
        self.assertIn("^[ \\t]*### Phase", checker)
        self.assertNotIn('Matches($content, "### Phase")', checker)


if __name__ == "__main__":
    unittest.main()
