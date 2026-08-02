#!/bin/bash
# skill_dir.sh — find where a skill is installed
# Usage: source skill_dir.sh <skill-name>
# Sets SKILL_DIR env var; exits 1 if not found.
SKILL_NAME="$1"
SKILL_DIR=""
for d in \
  "$HOME/.claude/skills/$SKILL_NAME" \
  "$HOME/.config/opencode/skills/$SKILL_NAME" \
  "$HOME/.agents/skills/$SKILL_NAME"; do
  [ -d "$d/scripts" ] && { SKILL_DIR="$d"; break; }
done
# Portable exit/return — works both sourced and standalone
[ -n "$SKILL_DIR" ] || { echo "✗ Not installed — run: npx @vitorlc/skills $SKILL_NAME"; return 1 2>/dev/null || exit 1; }