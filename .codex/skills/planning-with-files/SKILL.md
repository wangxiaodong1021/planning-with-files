---
name: planning-with-files
description: Implements Manus-style file-based planning to organize and track progress on complex tasks. Creates task_plan.md, findings.md, and progress.md. Use when asked to plan out, break down, or organize a multi-step project, research task, or any work requiring 5+ tool calls. Supports automatic session recovery after /clear.
user-invocable: true
allowed-tools: "Read Write Edit Bash Glob Grep"
hooks:
  UserPromptSubmit:
    - hooks:
        - type: command
          command: "if [ -f task_plan.md ]; then echo '[planning-with-files] ACTIVE PLAN — current state:'; head -50 task_plan.md; echo ''; echo '=== recent progress ==='; tail -20 progress.md 2>/dev/null; echo ''; echo '[planning-with-files] Read findings.md for research context. Continue from the current phase.'; fi"
  PreToolUse:
    - matcher: "Write|Edit|Bash|Read|Glob|Grep"
      hooks:
        - type: command
          command: "cat task_plan.md 2>/dev/null | head -30 || true"
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: "if [ -f task_plan.md ]; then echo '[planning-with-files] Update progress.md with what you just did. If a phase is now complete, update task_plan.md status.'; fi"
  Stop:
    - hooks:
        - type: command
          command: "SD=\"${CODEX_SKILL_ROOT:-$HOME/.codex/skills/planning-with-files}/scripts\"; powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"$SD/check-complete.ps1\" 2>/dev/null || sh \"$SD/check-complete.sh\""
metadata:
  version: "2.36.3-local-merged"

---

# Planning with Files

Work like Manus: Use persistent markdown files as your "working memory on disk."

## FIRST: Check for Previous Session (v2.2.0)

**Before starting work**, check for unsynced context from a previous session:

```bash
# Linux/macOS (auto-detects python3 or python)
$(command -v python3 || command -v python) ~/.codex/skills/planning-with-files/scripts/session-catchup.py "$(pwd)"
```

```powershell
# Windows PowerShell
python "$env:USERPROFILE\.codex\skills\planning-with-files\scripts\session-catchup.py" (Get-Location)
```

If catchup report shows unsynced context:
1. Run `git diff --stat` to see actual code changes
2. Read current planning files
3. Update planning files based on catchup + git diff
4. Then proceed with task

When hooks provide `$CODEX_PLAN_DIR`, catchup uses that directory to decide whether a plan is active and reports the full paths to the active `task_plan.md`, `progress.md`, and `findings.md`.

## Important: Where Files Go

- **Templates** are in `~/.codex/skills/planning-with-files/templates/`
- **Your planning files** go in `$CODEX_PLAN_DIR` when the Codex hooks set it.
- If `$CODEX_PLAN_DIR` is not set, planning files go in **your project directory**.
- In multi-session repos, never overwrite another task's root `task_plan.md`; create a plan-scoped directory under `.planning/plans/<plan-id>/`.
- Bind Codex sessions to plans with `.planning/sessions/<session-id>.json`; the session id is runtime routing state, not the durable planning namespace.
- For a long-running task that must resume across sessions, pin it with a stable `PLAN_ID`; hooks resolve `.planning/plans/<PLAN_ID>/` ahead of the legacy root fallback.
- Subagents do not run planning hooks by default. They must explicitly opt in to this skill, for example via active/requested skill metadata or `CODEX_PLANNING_WITH_FILES=1`; `PLAN_ID` and `CODEX_PLAN_DIR` alone are not treated as opt-in.

### Parallel Planning Layout

Use plan directories as the durable task boundary, and session mappings as the runtime attachment boundary:

```text
.planning/
  project_findings.md
  decisions.md
  .active_plan
  plans/
    2026-05-03-task-a/
      task_plan.md
      findings.md
      progress.md
      metadata.json
  sessions/
    <session-id>.json
```

`sessions/<session-id>.json` should contain the target `plan_id` and optionally `plan_dir`. When `.planning/sessions/` exists, normal Codex sessions must be attached before hooks inject plan context or block on stop. If `.planning/sessions/` is absent, hooks keep legacy single-session behavior.

Create a new isolated plan and attach a session:

```bash
~/.codex/skills/planning-with-files/scripts/init-session.sh --attach-session "$CODEX_SESSION_ID" "Task title"
```

Attach another session to an existing plan:

```bash
~/.codex/skills/planning-with-files/scripts/set-active-plan.sh --attach-session "$CODEX_SESSION_ID" 2026-05-03-task-title
```

### Subagent Session-Level Planning

Use one parent plan plus one plan directory per opted-in subagent.

| Actor | Planning directory | Responsibility |
|-------|--------------------|----------------|
| Parent session | `$CODEX_PLAN_DIR`, `.planning/<PLAN_ID>/`, or `.codex/planning/<parent-session-id>/` | Owns the overall task plan and tracks direct subagents in `subagents.jsonl` |
| Opted-in subagent | `.codex/planning/<subagent-session-id>/` by default | Owns its own `task_plan.md`, `findings.md`, and `progress.md` |
| Long-running shared task | `.planning/<PLAN_ID>/` | Use only when one durable plan must intentionally continue across sessions |

Operational rules:

- A subagent must opt in through active/requested skill metadata or `CODEX_PLANNING_WITH_FILES=1`; parent plan variables alone do not enable hooks.
- Prefer child session-scoped directories for parallel subagents. Do not have multiple agents write the same `task_plan.md` unless the work is strictly serialized.
- When an opted-in subagent includes a parent session or parent plan id, the hook appends a structured event to the parent-owned `subagents.jsonl` and regenerates `subagents.md` from that JSONL.
- If the runtime does not execute hooks inside spawned subagents, the parent `SessionStart`, `UserPromptSubmit`, and `Stop` hooks scan recent Codex subagent session logs and backfill the same `subagents.jsonl` records for prompts that explicitly mention `planning-with-files`.
- Treat `subagents.jsonl` as the durable machine state. `subagents.md` is a human-readable dashboard only and can be regenerated.
- For nested subagents, record each child under its direct parent's planning directory. A grandchild should update the child plan's `subagents.jsonl`, not the root plan directly.
- Use `PLAN_ID` for a subagent only when it is supposed to join a shared long-running plan, not for ordinary parallel helper tasks.

| Location | What Goes There |
|----------|-----------------|
| Skill directory (`~/.codex/skills/planning-with-files/`) | Templates, scripts, reference docs |
| `$CODEX_PLAN_DIR` or your project directory | `task_plan.md`, `findings.md`, `progress.md`, optional `subagents.jsonl` and generated `subagents.md` |

## Quick Start

Before ANY complex task:

1. **Create `task_plan.md`** in `$CODEX_PLAN_DIR` if set, otherwise in the project root — Use [templates/task_plan.md](templates/task_plan.md) as reference
2. **Create `findings.md`** in the same directory — Use [templates/findings.md](templates/findings.md) as reference
3. **Create `progress.md`** in the same directory — Use [templates/progress.md](templates/progress.md) as reference
4. **Re-read plan before decisions** — Refreshes goals in attention window
5. **Update after each phase** — Mark complete, log errors

> **Note:** Planning files go in your project root, not the skill installation folder.

## The Core Pattern

```
Context Window = RAM (volatile, limited)
Filesystem = Disk (persistent, unlimited)

→ Anything important gets written to disk.
```

## File Purposes

| File | Purpose | When to Update |
|------|---------|----------------|
| `task_plan.md` | Phases, progress, decisions | After each phase |
| `findings.md` | Research, discoveries | After ANY discovery |
| `progress.md` | Session log, test results | Throughout session |

## Critical Rules

### 1. Create Plan First
Never start a complex task without `task_plan.md`. Non-negotiable.

### 2. The 2-Action Rule
> "After every 2 view/browser/search operations, IMMEDIATELY save key findings to text files."

This prevents visual/multimodal information from being lost.

### 3. Read Before Decide
Before major decisions, read the plan file. This keeps goals in your attention window.

### 4. Update After Act
After completing any phase:
- Mark phase status: `in_progress` → `complete`
- Log any errors encountered
- Note files created/modified

### 5. Log ALL Errors
Every error goes in the plan file. This builds knowledge and prevents repetition.

```markdown
## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| FileNotFoundError | 1 | Created default config |
| API timeout | 2 | Added retry logic |
```

### 6. Never Repeat Failures
```
if action_failed:
    next_action != same_action
```
Track what you tried. Mutate the approach.

## The 3-Strike Error Protocol

```
ATTEMPT 1: Diagnose & Fix
  → Read error carefully
  → Identify root cause
  → Apply targeted fix

ATTEMPT 2: Alternative Approach
  → Same error? Try different method
  → Different tool? Different library?
  → NEVER repeat exact same failing action

ATTEMPT 3: Broader Rethink
  → Question assumptions
  → Search for solutions
  → Consider updating the plan

AFTER 3 FAILURES: Escalate to User
  → Explain what you tried
  → Share the specific error
  → Ask for guidance
```

## Read vs Write Decision Matrix

| Situation | Action | Reason |
|-----------|--------|--------|
| Just wrote a file | DON'T read | Content still in context |
| Viewed image/PDF | Write findings NOW | Multimodal → text before lost |
| Browser returned data | Write to file | Screenshots don't persist |
| Starting new phase | Read plan/findings | Re-orient if context stale |
| Error occurred | Read relevant file | Need current state to fix |
| Resuming after gap | Read all planning files | Recover state |

## The 5-Question Reboot Test

If you can answer these, your context management is solid:

| Question | Answer Source |
|----------|---------------|
| Where am I? | Current phase in task_plan.md |
| Where am I going? | Remaining phases |
| What's the goal? | Goal statement in plan |
| What have I learned? | findings.md |
| What have I done? | progress.md |

## When to Use This Pattern

**Use for:**
- Multi-step tasks (3+ steps)
- Research tasks
- Building/creating projects
- Tasks spanning many tool calls
- Anything requiring organization

**Skip for:**
- Simple questions
- Single-file edits
- Quick lookups

## Templates

Copy these templates to start:

- [templates/task_plan.md](templates/task_plan.md) — Phase tracking
- [templates/findings.md](templates/findings.md) — Research storage
- [templates/progress.md](templates/progress.md) — Session logging

## Scripts

Helper scripts for automation:

- `scripts/init-session.sh` — Initialize all planning files
- `scripts/check-complete.sh` — Verify all phases complete
- `scripts/session-catchup.py` — Recover context from previous session (v2.2.0)

## Advanced Topics

- **Manus Principles:** See [references/reference.md](references/reference.md)
- **Real Examples:** See [references/examples.md](references/examples.md)

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| Use TodoWrite for persistence | Create task_plan.md file |
| State goals once and forget | Re-read plan before decisions |
| Hide errors and retry silently | Log errors to plan file |
| Stuff everything in context | Store large content in files |
| Start executing immediately | Create plan file FIRST |
| Repeat failed actions | Track attempts, mutate approach |
| Create files in skill directory | Create files in your project |
