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
| `.codex/hooks/*.py` | Local overlay | Codex Desktop/CLI adapter behavior lives here. |
| `.codex/hooks/*.sh` | Local overlay | Thin shell behavior used by Python adapters. |
| `.codex/hooks/tests/` | Local overlay | Regression tests for local runtime contract. |
| `.codex/skills/planning-with-files/SKILL.md` | Shared | Only add local notes that are required for installed Codex behavior. |
| `commands/plan-attest.md` | Shared | Keep upstream-compatible wording, with local resolver details where needed. |

The desired future direction is to keep upstream files pristine when practical and move local behavior into adapter modules. Until that refactor is done, local changes must stay concentrated in `.codex/` and be audited after every upstream update.

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

If Codex reports a hook error, add a regression test before fixing it. In particular, hook stdout format is part of the contract and must be parsed as JSON when Codex expects JSON.

## Practical Rule

Do not answer "the merge is safe" from a static diff alone. Run at least one direct hook invocation and one real Codex CLI invocation when the change touches `.codex/hooks`, `.codex/hooks.json`, or `.codex/skills/planning-with-files/SKILL.md`.
