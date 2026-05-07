#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None


HOOK_DIR = Path(__file__).resolve().parent
TRUE_VALUES = {"1", "true", "yes", "on", "active", "enabled"}
PLANNING_SKILL_IDS = {
    "planning-with-files",
    "planning_with_files",
    "pi-planning-with-files",
}


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def cwd_from_payload(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd:
        return Path(cwd)
    return Path.cwd()


def _path_get(mapping: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in TRUE_VALUES)


def _clean_string(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return None


def contains_key(value: Any, key_name: str) -> bool:
    if isinstance(value, dict):
        if key_name in value:
            return True
        return any(contains_key(child, key_name) for child in value.values())
    if isinstance(value, list):
        return any(contains_key(child, key_name) for child in value)
    return False


def is_subagent_payload(payload: dict[str, Any]) -> bool:
    return contains_key(payload, "subagent") or contains_key(payload, "thread_spawn")


def _string_names_planning_skill(value: str) -> bool:
    normalized = value.strip().lower().replace("_", "-")
    return any(skill_id.replace("_", "-") in normalized for skill_id in PLANNING_SKILL_IDS)


def _contains_planning_skill(value: Any) -> bool:
    if isinstance(value, str):
        return _string_names_planning_skill(value)
    if isinstance(value, dict):
        if any(_string_names_planning_skill(str(key)) for key in value):
            return True
        return any(_contains_planning_skill(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_planning_skill(child) for child in value)
    return False


def planning_skill_opted_in(payload: dict[str, Any]) -> bool:
    for key in (
        "planning_with_files",
        "planning_with_files_active",
        "planning_hook_active",
        "use_planning_with_files",
    ):
        value = payload.get(key)
        if value is True or (isinstance(value, str) and _truthy(value)):
            return True

    for path in (
        ("metadata", "planning_with_files"),
        ("metadata", "planning_with_files_active"),
        ("_meta", "planning_with_files"),
        ("_meta", "planning_with_files_active"),
    ):
        value = _path_get(payload, path)
        if value is True or (isinstance(value, str) and _truthy(value)):
            return True

    for key in (
        "active_skills",
        "requested_skills",
        "enabled_skills",
        "skills",
        "skill",
    ):
        if _contains_planning_skill(payload.get(key)):
            return True

    for path in (
        ("metadata", "active_skills"),
        ("metadata", "requested_skills"),
        ("metadata", "enabled_skills"),
        ("metadata", "skills"),
        ("_meta", "active_skills"),
        ("_meta", "requested_skills"),
        ("_meta", "enabled_skills"),
        ("_meta", "skills"),
    ):
        if _contains_planning_skill(_path_get(payload, path)):
            return True

    for env_key in (
        "CODEX_PLANNING_WITH_FILES",
        "CODEX_PLANNING_WITH_FILES_ACTIVE",
        "PLANNING_WITH_FILES",
        "PLANNING_WITH_FILES_ACTIVE",
    ):
        if _truthy(os.environ.get(env_key)):
            return True

    for path in (
        ("prompt",),
        ("message",),
        ("user_message",),
        ("input",),
        ("instructions",),
        ("metadata", "prompt"),
        ("metadata", "message"),
        ("metadata", "user_message"),
        ("_meta", "prompt"),
        ("_meta", "message"),
        ("_meta", "user_message"),
    ):
        value = _path_get(payload, path)
        if isinstance(value, str) and _string_names_planning_skill(value):
            return True

    return False


def should_skip_planning_for_subagent(payload: dict[str, Any]) -> bool:
    return is_subagent_payload(payload) and not planning_skill_opted_in(payload)


def _first_payload_string(
    payload: dict[str, Any],
    keys: tuple[str, ...],
    paths: tuple[tuple[str, ...], ...] = (),
    env_keys: tuple[str, ...] = (),
) -> str | None:
    for key in keys:
        value = _clean_string(payload.get(key))
        if value:
            return value

    for path in paths:
        value = _clean_string(_path_get(payload, path))
        if value:
            return value

    for env_key in env_keys:
        value = _clean_string(os.environ.get(env_key))
        if value:
            return value

    return None


def plan_key_from_payload(payload: dict[str, Any]) -> str | None:
    for key in ("plan_id", "task_id", "planning_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    for path in (
        ("plan", "id"),
        ("task", "id"),
        ("metadata", "plan_id"),
        ("metadata", "task_id"),
        ("_meta", "plan_id"),
        ("_meta", "task_id"),
    ):
        value = _path_get(payload, path)
        if isinstance(value, str) and value:
            return value

    for env_key in ("PLAN_ID", "CODEX_PLAN_ID", "CODEX_TASK_ID"):
        value = os.environ.get(env_key)
        if value:
            return value

    return None


def parent_plan_key_from_payload(payload: dict[str, Any]) -> str | None:
    return _first_payload_string(
        payload,
        (
            "parent_plan_id",
            "parent_task_id",
            "parent_planning_id",
        ),
        (
            ("parent", "plan_id"),
            ("parent", "task_id"),
            ("parent", "planning_id"),
            ("thread_spawn", "parent_plan_id"),
            ("thread_spawn", "parent_task_id"),
            ("thread_spawn", "parent", "plan_id"),
            ("thread_spawn", "parent", "task_id"),
            ("metadata", "parent_plan_id"),
            ("metadata", "parent_task_id"),
            ("_meta", "parent_plan_id"),
            ("_meta", "parent_task_id"),
        ),
        (
            "CODEX_PARENT_PLAN_ID",
            "CODEX_PARENT_TASK_ID",
            "PARENT_PLAN_ID",
        ),
    )


def session_key_from_payload(payload: dict[str, Any]) -> str | None:
    for key in (
        "session_id",
        "thread_id",
        "conversation_id",
        "codex_session_id",
        "rollout_id",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value

    for path in (
        ("session", "id"),
        ("thread", "id"),
        ("conversation", "id"),
        ("metadata", "session_id"),
        ("metadata", "thread_id"),
        ("_meta", "session_id"),
        ("_meta", "thread_id"),
    ):
        value = _path_get(payload, path)
        if isinstance(value, str) and value:
            return value

    if is_subagent_payload(payload):
        value = _clean_string(payload.get("id"))
        if value:
            return value

    for env_key in (
        "CODEX_SESSION_ID",
        "CODEX_THREAD_ID",
        "CODEX_CONVERSATION_ID",
    ):
        value = os.environ.get(env_key)
        if value:
            return value

    return None


def parent_session_key_from_payload(payload: dict[str, Any]) -> str | None:
    return _first_payload_string(
        payload,
        (
            "parent_session_id",
            "parent_thread_id",
            "parent_conversation_id",
            "parent_codex_session_id",
            "parent_rollout_id",
        ),
        (
            ("parent", "session_id"),
            ("parent", "thread_id"),
            ("parent", "conversation_id"),
            ("parent", "codex_session_id"),
            ("parent", "rollout_id"),
            ("parent", "id"),
            ("thread_spawn", "parent_session_id"),
            ("thread_spawn", "parent_thread_id"),
            ("thread_spawn", "parent", "session_id"),
            ("thread_spawn", "parent", "thread_id"),
            ("thread_spawn", "parent", "id"),
            ("source", "subagent", "thread_spawn", "parent_session_id"),
            ("source", "subagent", "thread_spawn", "parent_thread_id"),
            ("source", "subagent", "thread_spawn", "parent", "session_id"),
            ("source", "subagent", "thread_spawn", "parent", "thread_id"),
            ("source", "subagent", "thread_spawn", "parent", "id"),
            ("metadata", "parent_session_id"),
            ("metadata", "parent_thread_id"),
            ("_meta", "parent_session_id"),
            ("_meta", "parent_thread_id"),
        ),
        (
            "CODEX_PARENT_SESSION_ID",
            "CODEX_PARENT_THREAD_ID",
            "CODEX_PARENT_CONVERSATION_ID",
        ),
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return slug[:96] or "session"


def _path_from_string(value: str, cwd: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else cwd / path


def _planning_root(cwd: Path) -> Path:
    return cwd / ".planning"


def _plan_container(cwd: Path) -> Path:
    return _planning_root(cwd) / "plans"


def _plan_dir_for_id(cwd: Path, plan_id: str) -> Path:
    slug = _slug(plan_id)
    preferred = _plan_container(cwd) / slug
    if preferred.exists() or not (_planning_root(cwd) / slug).exists():
        return preferred
    return _planning_root(cwd) / slug


def _plan_dir_exists(path: Path) -> bool:
    return path.is_dir() and (path / "task_plan.md").is_file()


def _read_session_plan_mapping(cwd: Path, session_key: str | None) -> dict[str, Any] | None:
    if not session_key:
        return None
    sessions_dir = _planning_root(cwd) / "sessions"
    if not sessions_dir.exists():
        return None

    safe_key = _slug(session_key)
    json_file = sessions_dir / f"{safe_key}.json"
    if json_file.exists():
        try:
            value = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict):
            return value

    attached_file = sessions_dir / f"{safe_key}.attached"
    if attached_file.exists():
        try:
            content = attached_file.read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        return {"session_id": session_key, "plan_id": content or None, "mode": "attached"}

    return None


def _planning_dir_from_session_mapping(cwd: Path, mapping: dict[str, Any] | None) -> Path | None:
    if not mapping:
        return None

    plan_dir = _clean_string(mapping.get("plan_dir"))
    if plan_dir:
        candidate = _path_from_string(plan_dir, cwd)
        if _plan_dir_exists(candidate):
            return candidate

    plan_id = _clean_string(mapping.get("plan_id"))
    if plan_id:
        candidate = _plan_dir_for_id(cwd, plan_id)
        if _plan_dir_exists(candidate):
            return candidate

    return None


def session_is_attached(payload: dict[str, Any], cwd: Path) -> bool:
    sessions_dir = _planning_root(cwd) / "sessions"
    if not sessions_dir.exists():
        return True
    return _read_session_plan_mapping(cwd, session_key_from_payload(payload)) is not None


def explicit_planning_dir_from_payload(payload: dict[str, Any], cwd: Path) -> Path | None:
    override = os.environ.get("CODEX_PLAN_DIR")
    if override:
        return _path_from_string(override, cwd)

    mapping_dir = _planning_dir_from_session_mapping(
        cwd,
        _read_session_plan_mapping(cwd, session_key_from_payload(payload)),
    )
    if mapping_dir is not None:
        return mapping_dir

    plan_key = plan_key_from_payload(payload)
    if plan_key:
        return _plan_dir_for_id(cwd, plan_key)

    session_key = session_key_from_payload(payload)
    if session_key and is_subagent_payload(payload):
        return cwd / ".codex" / "planning" / _slug(session_key)

    return None


def planning_dir_from_payload(payload: dict[str, Any], cwd: Path) -> Path:
    return explicit_planning_dir_from_payload(payload, cwd) or cwd


def parent_planning_dir_from_payload(payload: dict[str, Any], cwd: Path) -> Path | None:
    override = _first_payload_string(
        payload,
        ("parent_plan_dir", "parent_planning_dir"),
        (
            ("parent", "plan_dir"),
            ("parent", "planning_dir"),
            ("thread_spawn", "parent_plan_dir"),
            ("thread_spawn", "parent", "plan_dir"),
            ("metadata", "parent_plan_dir"),
            ("metadata", "parent_planning_dir"),
            ("_meta", "parent_plan_dir"),
            ("_meta", "parent_planning_dir"),
        ),
        ("CODEX_PARENT_PLAN_DIR", "CODEX_PARENT_PLANNING_DIR"),
    )
    if override:
        return _path_from_string(override, cwd)

    parent_plan_key = parent_plan_key_from_payload(payload)
    if parent_plan_key:
        return _plan_dir_for_id(cwd, parent_plan_key)

    parent_session_key = parent_session_key_from_payload(payload)
    if parent_session_key:
        return cwd / ".codex" / "planning" / _slug(parent_session_key)

    return None


def hook_env(payload: dict[str, Any], cwd: Path) -> dict[str, str]:
    env = os.environ.copy()
    plan_dir = explicit_planning_dir_from_payload(payload, cwd)
    parent_plan_dir = parent_planning_dir_from_payload(payload, cwd)
    if plan_dir is not None:
        env["CODEX_PLAN_DIR"] = str(plan_dir)
    else:
        env.pop("CODEX_PLAN_DIR", None)
    session_id = session_key_from_payload(payload) or ""
    if session_id:
        env["PWF_SESSION_ID"] = session_id
    env["CODEX_PLAN_ID"] = plan_key_from_payload(payload) or ""
    env["CODEX_PLAN_SESSION_ID"] = session_id
    env["CODEX_PARENT_PLAN_DIR"] = str(parent_plan_dir or "")
    env["CODEX_PARENT_PLAN_ID"] = parent_plan_key_from_payload(payload) or ""
    env["CODEX_PARENT_PLAN_SESSION_ID"] = parent_session_key_from_payload(payload) or ""
    return env


def subagent_key_from_payload(payload: dict[str, Any]) -> str:
    return (
        session_key_from_payload(payload)
        or _first_payload_string(
            payload,
            ("subagent_id", "agent_id"),
            (
                ("subagent", "id"),
                ("subagent", "agent_id"),
                ("thread_spawn", "subagent_id"),
                ("thread_spawn", "agent_id"),
                ("source", "subagent", "thread_spawn", "agent_path"),
                ("source", "subagent", "thread_spawn", "subagent_id"),
                ("source", "subagent", "thread_spawn", "agent_id"),
                ("metadata", "subagent_id"),
                ("metadata", "agent_id"),
                ("_meta", "subagent_id"),
                ("_meta", "agent_id"),
            ),
        )
        or "subagent"
    )


def subagent_role_from_payload(payload: dict[str, Any]) -> str:
    return (
        _first_payload_string(
            payload,
            ("subagent_role", "agent_role", "role"),
            (
                ("subagent", "role"),
                ("thread_spawn", "role"),
                ("thread_spawn", "agent_role"),
                ("source", "subagent", "thread_spawn", "role"),
                ("source", "subagent", "thread_spawn", "agent_role"),
                ("metadata", "subagent_role"),
                ("metadata", "agent_role"),
                ("_meta", "subagent_role"),
                ("_meta", "agent_role"),
            ),
        )
        or "subagent"
    )


def subagent_name_from_payload(payload: dict[str, Any]) -> str:
    return (
        _first_payload_string(
            payload,
            ("subagent_name", "agent_name", "nickname"),
            (
                ("subagent", "name"),
                ("subagent", "nickname"),
                ("thread_spawn", "name"),
                ("thread_spawn", "nickname"),
                ("thread_spawn", "agent_nickname"),
                ("source", "subagent", "thread_spawn", "name"),
                ("source", "subagent", "thread_spawn", "nickname"),
                ("source", "subagent", "thread_spawn", "agent_nickname"),
                ("metadata", "subagent_name"),
                ("metadata", "agent_name"),
                ("_meta", "subagent_name"),
                ("_meta", "agent_name"),
            ),
        )
        or ""
    )


def subagent_task_from_payload(payload: dict[str, Any]) -> str:
    task = _first_payload_string(
        payload,
        ("subtask", "task", "task_summary", "prompt", "message", "instructions"),
        (
            ("subagent", "task"),
            ("subagent", "task_summary"),
            ("thread_spawn", "task"),
            ("thread_spawn", "prompt"),
            ("metadata", "subtask"),
            ("metadata", "task"),
            ("metadata", "task_summary"),
            ("_meta", "subtask"),
            ("_meta", "task"),
            ("_meta", "task_summary"),
        ),
    )
    if not task:
        return ""
    return re.sub(r"\s+", " ", task).strip()[:240]


def _markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", r"\|")


def _subagent_index_header() -> list[str]:
    return [
        "# Subagent Planning Index",
        "",
        "Generated from `subagents.jsonl` by the planning-with-files hook. Treat the JSONL file as the durable source of truth.",
        "",
        "| Child key | Parent key | Role | Name | Task | Plan directory | Plan ID | Last seen hook | Last seen UTC |",
        "|-----------|------------|------|------|------|----------------|---------|----------------|---------------|",
    ]


def _lock_file(lock_handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_handle: Any) -> None:
    if fcntl is not None:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _subagent_event_from_payload(
    payload: dict[str, Any],
    cwd: Path,
    parent_plan_dir: Path,
    hook_name: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "event": "subagent_seen",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook_name": hook_name,
        "child_key": subagent_key_from_payload(payload),
        "parent_key": parent_session_key_from_payload(payload) or parent_plan_key_from_payload(payload) or "",
        "role": subagent_role_from_payload(payload),
        "name": subagent_name_from_payload(payload),
        "task": subagent_task_from_payload(payload),
        "plan_dir": str(planning_dir_from_payload(payload, cwd)),
        "plan_id": plan_key_from_payload(payload) or "",
        "parent_plan_dir": str(parent_plan_dir),
    }


def _subagent_event_from_session_meta(
    meta: dict[str, Any],
    session_file: Path,
    parent_plan_dir: Path,
    hook_name: str,
    task: str,
    plan_dir: Path,
) -> dict[str, Any]:
    thread_spawn = _path_get(meta, ("source", "subagent", "thread_spawn"))
    if not isinstance(thread_spawn, dict):
        thread_spawn = {}
    return {
        "schema_version": 1,
        "event": "subagent_seen",
        "event_id": f"{session_file.stem}:{hook_name}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook_name": hook_name,
        "child_key": _clean_string(meta.get("id")) or session_file.stem,
        "parent_key": _clean_string(thread_spawn.get("parent_thread_id")) or "",
        "role": _clean_string(thread_spawn.get("agent_role")) or _clean_string(meta.get("agent_role")) or "subagent",
        "name": _clean_string(thread_spawn.get("agent_nickname")) or _clean_string(meta.get("agent_nickname")) or "",
        "task": re.sub(r"\s+", " ", task).strip()[:240],
        "plan_dir": str(plan_dir),
        "plan_id": "",
        "parent_plan_dir": str(parent_plan_dir),
        "session_file": str(session_file),
    }


def _read_subagent_events(jsonl_file: Path) -> list[dict[str, Any]]:
    if not jsonl_file.exists():
        return []

    events: list[dict[str, Any]] = []
    with jsonl_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event") == "subagent_seen":
                events.append(event)
    return events


def _subagent_event_seen(jsonl_file: Path, event_id: str | None) -> bool:
    if not event_id:
        return False
    return any(event.get("event_id") == event_id for event in _read_subagent_events(jsonl_file))


def _subagent_markdown_row(event: dict[str, Any]) -> str:
    return (
        "| "
        + " | ".join(
            [
                _markdown_cell(event.get("child_key", "")),
                _markdown_cell(event.get("parent_key", "")),
                _markdown_cell(event.get("role", "")),
                _markdown_cell(event.get("name", "")),
                _markdown_cell(event.get("task", "")),
                _markdown_cell(event.get("plan_dir", "")),
                _markdown_cell(event.get("plan_id", "")),
                _markdown_cell(event.get("hook_name", "")),
                _markdown_cell(event.get("timestamp_utc", "")),
            ]
        )
        + " |"
    )


def render_subagent_markdown_from_jsonl(parent_plan_dir: Path) -> Path:
    jsonl_file = parent_plan_dir / "subagents.jsonl"
    markdown_file = parent_plan_dir / "subagents.md"
    latest_by_child: dict[str, dict[str, Any]] = {}

    for event in _read_subagent_events(jsonl_file):
        child_key = _clean_string(event.get("child_key"))
        if child_key:
            latest_by_child[child_key] = event

    rows = [_subagent_markdown_row(event) for event in latest_by_child.values()]
    content = "\n".join(_subagent_index_header() + rows) + "\n"
    tmp_file = markdown_file.with_suffix(markdown_file.suffix + ".tmp")
    tmp_file.write_text(content, encoding="utf-8")
    tmp_file.replace(markdown_file)
    return markdown_file


def _append_subagent_event(parent_plan_dir: Path, event: dict[str, Any]) -> Path:
    parent_plan_dir.mkdir(parents=True, exist_ok=True)
    jsonl_file = parent_plan_dir / "subagents.jsonl"
    lock_file = parent_plan_dir / ".subagents.lock"
    with lock_file.open("a+", encoding="utf-8") as lock_handle:
        _lock_file(lock_handle)
        try:
            event_id = _clean_string(event.get("event_id"))
            if _subagent_event_seen(jsonl_file, event_id):
                render_subagent_markdown_from_jsonl(parent_plan_dir)
                return jsonl_file
            with jsonl_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            render_subagent_markdown_from_jsonl(parent_plan_dir)
        finally:
            _unlock_file(lock_handle)
    return jsonl_file


def record_subagent_planning_index(payload: dict[str, Any], cwd: Path, hook_name: str) -> Path | None:
    if not is_subagent_payload(payload) or not planning_skill_opted_in(payload):
        return None

    parent_plan_dir = parent_planning_dir_from_payload(payload, cwd)
    if parent_plan_dir is None:
        return None

    event = _subagent_event_from_payload(payload, cwd, parent_plan_dir, hook_name)
    _append_subagent_event(parent_plan_dir, event)
    return parent_plan_dir / "subagents.md"


def _iter_recent_session_files(sessions_dir: Path) -> list[Path]:
    if not sessions_dir.exists():
        return []
    try:
        files = [path for path in sessions_dir.rglob("rollout-*.jsonl") if path.is_file()]
    except OSError:
        return []
    files.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0, reverse=True)
    return files[:200]


def _read_session_meta(session_file: Path) -> dict[str, Any] | None:
    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "session_meta":
                    continue
                payload = data.get("payload")
                return payload if isinstance(payload, dict) else None
    except OSError:
        return None
    return None


def _session_user_message(session_file: Path) -> str:
    try:
        with session_file.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = data.get("payload")
                if not isinstance(payload, dict):
                    continue
                if data.get("type") == "event_msg" and payload.get("type") == "user_message":
                    message = payload.get("message")
                    return message if isinstance(message, str) else ""
                if data.get("type") == "response_item" and payload.get("type") == "message":
                    if payload.get("role") != "user":
                        continue
                    content = payload.get("content")
                    if isinstance(content, str):
                        return content
    except OSError:
        return ""
    return ""


def _extract_plan_dir_from_text(text: str, cwd: Path, fallback: Path) -> Path:
    pattern = r"((?:/|~)[^\s`'\"<>]*/\.codex/planning/[^\s`'\"<>]+)"
    match = re.search(pattern, text)
    if not match:
        return fallback
    raw = match.group(1).rstrip(".,;:)")
    path = Path(os.path.expanduser(raw))
    return path if path.is_absolute() else cwd / path


def record_spawned_subagents_from_session_logs(payload: dict[str, Any], cwd: Path, hook_name: str) -> list[Path]:
    if is_subagent_payload(payload):
        return []

    parent_key = session_key_from_payload(payload)
    if not parent_key:
        return []

    parent_plan_dir = explicit_planning_dir_from_payload(payload, cwd) or (
        cwd / ".codex" / "planning" / _slug(parent_key)
    )
    sessions_dir = Path(os.path.expanduser(os.environ.get("CODEX_SESSIONS_DIR", "~/.codex/sessions")))
    recorded: list[Path] = []

    for session_file in _iter_recent_session_files(sessions_dir):
        meta = _read_session_meta(session_file)
        if not meta:
            continue
        thread_spawn = _path_get(meta, ("source", "subagent", "thread_spawn"))
        if not isinstance(thread_spawn, dict):
            continue
        if _clean_string(thread_spawn.get("parent_thread_id")) != parent_key:
            continue

        task = _session_user_message(session_file)
        if not _string_names_planning_skill(task):
            continue

        child_key = _clean_string(meta.get("id")) or session_file.stem
        fallback_plan_dir = cwd / ".codex" / "planning" / _slug(child_key)
        child_plan_dir = _extract_plan_dir_from_text(task, cwd, fallback_plan_dir)
        event = _subagent_event_from_session_meta(
            meta,
            session_file,
            parent_plan_dir,
            hook_name,
            task,
            child_plan_dir,
        )
        _append_subagent_event(parent_plan_dir, event)
        recorded.append(parent_plan_dir / "subagents.md")

    return recorded


def emit_json(payload: dict[str, Any]) -> None:
    if not payload:
        return
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def parse_json(text: str) -> dict[str, Any]:
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def run_shell_script(script_name: str, cwd: Path, env: dict[str, str] | None = None) -> tuple[str, str]:
    result = subprocess.run(
        ["sh", str(HOOK_DIR / script_name)],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )
    return result.stdout.strip(), result.stderr.strip()


def main_guard(func) -> int:
    try:
        func()
    except Exception as exc:  # pragma: no cover
        print(f"[planning-with-files hook] {exc}", file=sys.stderr)
        return 0
    return 0
