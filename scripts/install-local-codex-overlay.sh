#!/bin/sh
# Install this repository's local Codex overlay into CODEX_HOME.

set -eu

DRY_RUN=0
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
  shift
fi

if [ "$#" -ne 0 ]; then
  echo "usage: $0 [--dry-run]" >&2
  exit 2
fi

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
BACKUP_DIR="$CODEX_HOME/backups/planning-with-files-overlay-$(date +%Y%m%d-%H%M%S)"

copy_dir() {
  src="$1"
  dst="$2"
  mkdir -p "$dst"
  if [ "$DRY_RUN" -eq 1 ]; then
    rsync -a --dry-run \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      "$src/" "$dst/"
  else
    rsync -a \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      "$src/" "$dst/"
  fi
}

copy_file() {
  src="$1"
  dst="$2"
  mkdir -p "$(dirname -- "$dst")"
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "copy $src -> $dst"
  else
    cp "$src" "$dst"
  fi
}

if [ ! -d "$REPO_ROOT/.codex/hooks" ]; then
  echo "missing repo hooks directory: $REPO_ROOT/.codex/hooks" >&2
  exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run install from $REPO_ROOT to $CODEX_HOME"
else
  mkdir -p "$BACKUP_DIR"
  [ ! -e "$CODEX_HOME/hooks.json" ] || cp "$CODEX_HOME/hooks.json" "$BACKUP_DIR/hooks.json"
  [ ! -d "$CODEX_HOME/hooks" ] || cp -R "$CODEX_HOME/hooks" "$BACKUP_DIR/hooks"
  [ ! -d "$CODEX_HOME/skills/planning-with-files" ] ||
    cp -R "$CODEX_HOME/skills/planning-with-files" "$BACKUP_DIR/planning-with-files"
  [ ! -f "$CODEX_HOME/commands/plan-attest.md" ] ||
    cp "$CODEX_HOME/commands/plan-attest.md" "$BACKUP_DIR/plan-attest.md"
  echo "backup: $BACKUP_DIR"
fi

copy_file "$REPO_ROOT/.codex/hooks.json" "$CODEX_HOME/hooks.json"
copy_dir "$REPO_ROOT/.codex/hooks" "$CODEX_HOME/hooks"
copy_dir "$REPO_ROOT/.codex/skills/planning-with-files" "$CODEX_HOME/skills/planning-with-files"
copy_file "$REPO_ROOT/commands/plan-attest.md" "$CODEX_HOME/commands/plan-attest.md"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry-run complete"
else
  find "$CODEX_HOME/hooks" -name __pycache__ -type d -prune -exec rm -rf {} +
  find "$CODEX_HOME/hooks" -name '*.pyc' -type f -delete
  chmod +x "$CODEX_HOME"/hooks/*.sh 2>/dev/null || true
  chmod +x "$CODEX_HOME"/skills/planning-with-files/scripts/*.sh 2>/dev/null || true
  echo "installed local Codex overlay"
fi
