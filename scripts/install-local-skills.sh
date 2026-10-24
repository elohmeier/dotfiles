#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

if [[ ! -d "$repo_root/skills" ]]; then
  echo "Skills directory not found in local checkout: $repo_root" >&2
  exit 1
fi

exec npx --yes skills add "$repo_root" "$@"
