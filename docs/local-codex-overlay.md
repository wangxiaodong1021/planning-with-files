# Local Codex Overlay Maintenance

This fork should be maintained as:

1. Upstream official `OthmanAdi/planning-with-files` history and tags.
2. A small local Codex overlay commit stack on top.

Do not treat the local `~/.codex` installation as the source of truth. The source of truth is this repository plus the local overlay commits after the latest upstream release tag.

## Why This Exists

The local Codex Desktop and Codex CLI runtime has behavior that upstream does not cover yet:

- `$CODEX_PLAN_DIR` routing.
- `.planning/plans/<plan-id>/` support.
- `.planning/sessions/<session-id>.json` attachment.
- Subagent opt-in planning indexes.
- Codex CLI hook JSON output compatibility.
- Local stop-hook false-positive fixes.

Past failures happened because upstream hook files and local runtime adapters were edited in the same places without a clear boundary. When upstream changed the hook contract, local code still passed old tests but failed in real Codex CLI runs.

## Ownership Boundary

Prefer this ownership split:

| Surface | Owner | Rule |
|---|---|---|
| Upstream files outside `.codex/` | Upstream | Keep as close to upstream as possible. |
| `.codex/hooks/codex_hook_adapter.py` | Upstream | Keep aligned with the current upstream release and do not add local runtime behavior here. |
| `.codex/hooks/local_codex_overlay.py` | Local overlay | Codex Desktop/CLI adapter behavior lives here. |
| `.codex/hooks/*_tool_use.py`, `stop.py`, `session_start.py`, `user_prompt_submit.py` | Local overlay entrypoints | Keep thin; call the adapter API and emit Codex-compatible JSON. |
| `.codex/hooks/*.sh` | Local overlay | Thin shell behavior used by Python adapters. |
| `.codex/hooks/tests/` | Local overlay | Regression tests for local runtime contract. |
| `.codex/skills/planning-with-files/SKILL.md` | Shared | Only add local notes that are required for installed Codex behavior. |
| `commands/plan-attest.md` | Shared | Keep upstream-compatible wording, with local resolver details where needed. |

The local adapter behavior is concentrated in `.codex/hooks/local_codex_overlay.py`. Keep entrypoint wrappers thin and avoid spreading local-only routing logic into upstream mirror files. In particular, do not re-edit `.codex/hooks/codex_hook_adapter.py` for local Codex behavior; leave it as the upstream comparison anchor.

## Update Workflow

Use this flow for every upstream release:

```bash
git fetch upstream --tags
git checkout master
git merge --ff-only upstream/master
scripts/audit-local-codex-overlay.sh --cli
```

If `--ff-only` fails because local overlay commits are already on top, use a rebase:

```bash
git fetch upstream --tags
git rebase upstream/master
scripts/audit-local-codex-overlay.sh --cli
```

Resolve conflicts by preferring upstream behavior first, then re-apply only the local Codex runtime requirement that is still missing upstream.

## Required Checks

After every merge or rebase, the audit must pass:

- Local overlay file list is understood.
- `UserPromptSubmit` emits valid JSON.
- Hook unit tests pass.
- Python hook files compile.
- Optional real `codex exec` smoke test passes when `--cli` is used.

## Install The Local Overlay

After the repository state is verified, install it into the local Codex runtime:

```bash
scripts/install-local-codex-overlay.sh --dry-run
scripts/install-local-codex-overlay.sh
```

The installer backs up the current local hooks, skill, `hooks.json`, and `/plan-attest` command under `~/.codex/backups/` before copying the repository overlay into `~/.codex`.

If Codex reports a hook error, add a regression test before fixing it. In particular, hook stdout format is part of the contract and must be parsed as JSON when Codex expects JSON.

## Practical Rule

Do not answer "the merge is safe" from a static diff alone. Run at least one direct hook invocation and one real Codex CLI invocation when the change touches `.codex/hooks`, `.codex/hooks.json`, or `.codex/skills/planning-with-files/SKILL.md`.
