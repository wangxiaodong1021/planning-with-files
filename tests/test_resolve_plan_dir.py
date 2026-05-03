"""Tests for scripts/resolve-plan-dir.sh — addresses #148.

Resolver order:
  1. $CODEX_PLAN_DIR env if it contains task_plan.md
  2. $PLAN_ID env → .planning/plans/<id>/, then .planning/<id>/
  3. .planning/.active_plan content → matching plan dir
  4. Newest .planning/plans/<dir>/, then .planning/<dir>/ by mtime
  5. Legacy fallback: <cwd>/task_plan.md exists → emit empty (caller uses cwd)
  6. Otherwise empty stdout, exit 0
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVE_SH = REPO_ROOT / "scripts" / "resolve-plan-dir.sh"


class ResolvePlanDirTests(unittest.TestCase):
    def run_resolver(
        self,
        cwd: Path,
        plan_id: str | None = None,
        codex_plan_dir: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("PLAN_ID", None)
        env.pop("CODEX_PLAN_DIR", None)
        if plan_id is not None:
            env["PLAN_ID"] = plan_id
        if codex_plan_dir is not None:
            env["CODEX_PLAN_DIR"] = codex_plan_dir
        return subprocess.run(
            ["sh", str(RESOLVE_SH)],
            cwd=str(cwd),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_resolver_script_exists(self) -> None:
        self.assertTrue(RESOLVE_SH.exists(), "scripts/resolve-plan-dir.sh missing")

    def test_empty_repo_returns_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_resolver(Path(tmp))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    def test_env_plan_id_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".planning" / "plans" / "alpha").mkdir(parents=True)
            (root / ".planning" / "plans" / "beta").mkdir(parents=True)
            (root / ".planning" / "plans" / "alpha" / "task_plan.md").write_text("# alpha\n", encoding="utf-8")
            (root / ".planning" / "plans" / "beta" / "task_plan.md").write_text("# beta\n", encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("beta\n", encoding="utf-8")
            result = self.run_resolver(root, plan_id="alpha")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.strip().endswith("alpha"))

    def test_active_plan_used_when_env_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".planning" / "plans" / "alpha").mkdir(parents=True)
            (root / ".planning" / "plans" / "beta").mkdir(parents=True)
            (root / ".planning" / "plans" / "alpha" / "task_plan.md").write_text("# alpha\n", encoding="utf-8")
            (root / ".planning" / "plans" / "beta" / "task_plan.md").write_text("# beta\n", encoding="utf-8")
            (root / ".planning" / ".active_plan").write_text("beta\n", encoding="utf-8")
            result = self.run_resolver(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.strip().endswith("beta"))

    def test_falls_back_to_newest_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = root / ".planning" / "plans" / "older"
            new = root / ".planning" / "plans" / "newer"
            old.mkdir(parents=True)
            (old / "task_plan.md").write_text("# old\n", encoding="utf-8")
            time.sleep(0.05)
            new.mkdir(parents=True)
            (new / "task_plan.md").write_text("# new\n", encoding="utf-8")
            # bump mtime explicitly to be safe across filesystems
            os.utime(new, None)
            result = self.run_resolver(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(
                result.stdout.strip().endswith("newer"),
                f"expected newer, got {result.stdout!r}",
            )

    def test_legacy_root_plan_emits_empty(self) -> None:
        # When no .planning/ but cwd/task_plan.md exists, resolver emits empty so
        # callers fall back to the legacy root path. This preserves v1.x users.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "task_plan.md").write_text("# legacy\n", encoding="utf-8")
            result = self.run_resolver(root)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())

    def test_codex_plan_dir_takes_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom = root / "custom-plan"
            custom.mkdir()
            (custom / "task_plan.md").write_text("# custom\n", encoding="utf-8")
            other = root / ".planning" / "plans" / "other"
            other.mkdir(parents=True)
            (other / "task_plan.md").write_text("# other\n", encoding="utf-8")
            result = self.run_resolver(root, plan_id="other", codex_plan_dir="custom-plan")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(result.stdout.strip().endswith("custom-plan"))

    def test_env_plan_id_pointing_to_missing_dir_falls_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / ".planning" / "plans" / "real"
            real.mkdir(parents=True)
            (real / "task_plan.md").write_text("# real plan\n", encoding="utf-8")
            result = self.run_resolver(root, plan_id="ghost")
            self.assertEqual(0, result.returncode, result.stderr)
            # Should fall through to newest existing plan dir
            self.assertTrue(result.stdout.strip().endswith("real"))


if __name__ == "__main__":
    unittest.main()
