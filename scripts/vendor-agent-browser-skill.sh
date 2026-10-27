#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/vendor-agent-browser-skill.sh [agent-browser-repo]

Vendors vercel-labs/agent-browser's skill-data/core skill into
skills/agent-browser and rewrites the skill frontmatter name to
agent-browser.

Arguments:
  agent-browser-repo  Path to the upstream checkout.

Environment:
  AGENT_BROWSER_REPO  Default upstream checkout path when no argument is given.
EOF
}

update_upstream_repo() {
  if ! command -v git >/dev/null 2>&1; then
    echo "git not found; cannot update upstream checkout" >&2
    exit 1
  fi

  if ! git -C "$upstream_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Upstream path is not a git checkout: $upstream_root" >&2
    exit 1
  fi

  if [[ -n "$(git -C "$upstream_root" status --porcelain)" ]]; then
    echo "Upstream checkout has local changes; refusing to update:" >&2
    git -C "$upstream_root" status --short >&2
    exit 1
  fi

  upstream_ref="$(git -C "$upstream_root" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)" || {
    echo "Upstream checkout has no tracking branch: $upstream_root" >&2
    exit 1
  }

  git -C "$upstream_root" fetch --prune
  git -C "$upstream_root" merge --ff-only "$upstream_ref"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_root="${1:-${AGENT_BROWSER_REPO:-/var/home/gordon/repos/github.com/vercel-labs/agent-browser}}"
source_dir="$upstream_root/skill-data/core"
dest_dir="$repo_root/skills/agent-browser"
dest_rel="skills/agent-browser"

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi

update_upstream_repo

if [[ ! -d "$source_dir" ]]; then
  echo "Source skill directory not found: $source_dir" >&2
  exit 1
fi

if [[ ! -f "$source_dir/SKILL.md" ]]; then
  echo "Source skill is missing SKILL.md: $source_dir" >&2
  exit 1
fi

mkdir -p "$(dirname "$dest_dir")"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '.DS_Store' "$source_dir"/ "$dest_dir"/
else
  tmp_copy="$(mktemp -d)"
  trap 'rm -rf "$tmp_copy"' EXIT
  cp -R "$source_dir"/. "$tmp_copy"/
  rm -rf "$dest_dir"
  mkdir -p "$dest_dir"
  cp -R "$tmp_copy"/. "$dest_dir"/
fi

skill_md="$dest_dir/SKILL.md"
tmp_skill="$(mktemp)"

awk '
  NR == 2 && $0 ~ /^name:/ {
    print "name: agent-browser"
    rewritten = 1
    next
  }
  { print }
  END {
    if (!rewritten) {
      exit 42
    }
  }
' "$skill_md" > "$tmp_skill" || {
  status=$?
  rm -f "$tmp_skill"
  if [[ $status -eq 42 ]]; then
    echo "Could not rewrite frontmatter name in $skill_md" >&2
    exit 1
  fi
  exit "$status"
}

mv "$tmp_skill" "$skill_md"

if ! grep -q '^name: agent-browser$' "$skill_md"; then
  echo "Vendored skill name was not updated to agent-browser" >&2
  exit 1
fi

if command -v dprint >/dev/null 2>&1; then
  (cd "$repo_root" && dprint fmt "$dest_rel/**/*.md")
else
  echo "dprint not found; skipping Markdown formatting" >&2
fi

echo "Vendored $source_dir -> $dest_dir"
