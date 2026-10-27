#!/usr/bin/env bash
set -euo pipefail

query="${1:-}"

if [[ -z "$query" ]]; then
  echo "Usage: $0 <query>" >&2
  echo "Examples: $0 tooltip | $0 GeoPath | $0 BarChart" >&2
  exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required" >&2
  exit 1
fi

declare -a roots=()

if [[ -d "$PWD/packages/layerchart/src" ]]; then
  roots+=("$PWD/packages/layerchart/src")
else
  [[ -d "$PWD/src" ]] && roots+=("$PWD/src")
  [[ -d "$PWD/node_modules/layerchart" ]] && roots+=("$PWD/node_modules/layerchart")
fi

if [[ ${#roots[@]} -eq 0 ]]; then
  roots+=("$PWD")
fi

echo "== Matching files =="
rg --files "${roots[@]}" \
  -g '!node_modules/.pnpm/**' \
  -g '!dist/**' \
  -g '!build/**' \
  -g '*.svelte' \
  -g '*.ts' \
  -g '*.js' \
  2>/dev/null | rg -i "$query" | sed -n '1,80p' || true

echo
echo "== Matching references =="
rg -n -i "$query" "${roots[@]}" \
  -g '!node_modules/.pnpm/**' \
  -g '!dist/**' \
  -g '!build/**' \
  -g '*.svelte' \
  -g '*.ts' \
  -g '*.js' \
  2>/dev/null | sed -n '1,120p' || true
