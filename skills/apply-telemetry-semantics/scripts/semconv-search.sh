#!/usr/bin/env bash

set -uo pipefail

usage() {
  printf '%s\n' \
    'Usage: semconv-search.sh [--ecs|--otel|--both] [--primary|--readable|--all-sources]' \
    '                             [--regex] [--ecs-ref REF]' \
    '                             [--otel-ref REF|--ecs-aligned] QUERY' \
    '' \
    'Search ECS/OpenTelemetry sources in local Git clones. Canonical sources and' \
    'the expanded ECS field locator are searched by default. Fixed-string search' \
    'is the default. Repository roots can be overridden with:' \
    '  ECS_REPO_PATH and OTEL_SEMCONV_REPO_PATH'
}

source_selection=both
search_scope=primary
search_mode=fixed
ecs_ref=
otel_ref=

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ecs)
      source_selection=ecs
      shift
      ;;
    --otel)
      source_selection=otel
      shift
      ;;
    --both)
      source_selection=both
      shift
      ;;
    --primary)
      search_scope=primary
      shift
      ;;
    --readable)
      search_scope=readable
      shift
      ;;
    --all-sources)
      search_scope=all
      shift
      ;;
    --regex)
      search_mode=regex
      shift
      ;;
    --ecs-ref)
      if [ "$#" -lt 2 ]; then
        usage >&2
        exit 2
      fi
      ecs_ref=$2
      shift 2
      ;;
    --otel-ref)
      if [ "$#" -lt 2 ]; then
        usage >&2
        exit 2
      fi
      otel_ref=$2
      shift 2
      ;;
    --ecs-aligned)
      otel_ref=__ECS_ALIGNED__
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -* )
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      break
      ;;
  esac
done

if [ "$#" -eq 0 ]; then
  usage >&2
  exit 2
fi

query=$1
shift
while [ "$#" -gt 0 ]; do
  query="$query $1"
  shift
done

ecs_root=${ECS_REPO_PATH:-/Users/enno/repos/github.com/elastic/ecs}
otel_root=${OTEL_SEMCONV_REPO_PATH:-/Users/enno/repos/github.com/open-telemetry/semantic-conventions}
found=0

require_repo() {
  local repo_name=$1
  local repo_root=$2
  if ! git -C "$repo_root" rev-parse --git-dir >/dev/null 2>&1; then
    printf '%s repository is unavailable: %s\n' "$repo_name" "$repo_root" >&2
    exit 2
  fi
}

describe_repo() {
  local repo_name=$1
  local repo_root=$2
  local repo_description
  repo_description=$(git -C "$repo_root" describe --tags --always --dirty 2>/dev/null || git -C "$repo_root" rev-parse --short HEAD)
  printf '%s: %s (%s)\n' "$repo_name" "$repo_root" "$repo_description"
}

search_worktree() {
  local label=$1
  shift
  printf '\n[%s]\n' "$label"
  if [ "$search_mode" = fixed ]; then
    if rg -n --color never -F -- "$query" "$@"; then
      found=1
    else
      printf '(no matches)\n'
    fi
  else
    if rg -n --color never -- "$query" "$@"; then
      found=1
    else
      printf '(no matches)\n'
    fi
  fi
}

search_git_ref() {
  local label=$1
  local repo_root=$2
  local ref=$3
  shift 3
  if ! git -C "$repo_root" rev-parse --verify "$ref^{commit}" >/dev/null 2>&1; then
    printf 'Git ref is unavailable in %s: %s\n' "$repo_root" "$ref" >&2
    exit 2
  fi
  printf '\n[%s at %s]\n' "$label" "$ref"
  if [ "$search_mode" = fixed ]; then
    if git -C "$repo_root" grep -n -F -e "$query" "$ref" -- "$@"; then
      found=1
    else
      printf '(no matches)\n'
    fi
  else
    if git -C "$repo_root" grep -n -E -e "$query" "$ref" -- "$@"; then
      found=1
    else
      printf '(no matches)\n'
    fi
  fi
}

if [ "$source_selection" = ecs ] || [ "$source_selection" = both ]; then
  require_repo ECS "$ecs_root"
  describe_repo ECS "$ecs_root"
  if [ -f "$ecs_root/version" ]; then
    printf 'ECS model version: %s\n' "$(sed -n '1p' "$ecs_root/version")"
  fi
  if [ -f "$ecs_root/otel-semconv-version" ]; then
    printf 'ECS OTel alignment ref: %s\n' "$(sed -n '1p' "$ecs_root/otel-semconv-version")"
  fi
  if [ -n "$ecs_ref" ]; then
    if [ "$search_scope" = primary ] || [ "$search_scope" = all ]; then
      search_git_ref 'ECS canonical schemas' "$ecs_root" "$ecs_ref" schemas
      search_git_ref 'ECS expanded fields' "$ecs_root" "$ecs_ref" generated/ecs/ecs_flat.yml
    fi
    if [ "$search_scope" = readable ] || [ "$search_scope" = all ]; then
      search_git_ref 'ECS readable guidance and mappings' "$ecs_root" "$ecs_ref" docs/reference
    fi
  else
    if [ "$search_scope" = primary ] || [ "$search_scope" = all ]; then
      search_worktree 'ECS canonical schemas' "$ecs_root/schemas"
      search_worktree 'ECS expanded fields' "$ecs_root/generated/ecs/ecs_flat.yml"
    fi
    if [ "$search_scope" = readable ] || [ "$search_scope" = all ]; then
      search_worktree 'ECS readable guidance and mappings' "$ecs_root/docs/reference"
    fi
  fi
fi

if [ "$source_selection" = otel ] || [ "$source_selection" = both ]; then
  require_repo OpenTelemetry "$otel_root"
  describe_repo OpenTelemetry "$otel_root"
  if [ "$otel_ref" = __ECS_ALIGNED__ ]; then
    require_repo ECS "$ecs_root"
    if [ ! -f "$ecs_root/otel-semconv-version" ]; then
      printf 'Missing ECS alignment pin: %s/otel-semconv-version\n' "$ecs_root" >&2
      exit 2
    fi
    otel_ref=$(sed -n '1p' "$ecs_root/otel-semconv-version")
  fi
  if [ -n "$otel_ref" ]; then
    if [ "$search_scope" = primary ] || [ "$search_scope" = all ]; then
      search_git_ref 'OpenTelemetry canonical model' "$otel_root" "$otel_ref" model
    fi
    if [ "$search_scope" = readable ] || [ "$search_scope" = all ]; then
      search_git_ref 'OpenTelemetry readable conventions' "$otel_root" "$otel_ref" docs
    fi
  else
    if [ "$search_scope" = primary ] || [ "$search_scope" = all ]; then
      search_worktree 'OpenTelemetry canonical model' "$otel_root/model"
    fi
    if [ "$search_scope" = readable ] || [ "$search_scope" = all ]; then
      search_worktree 'OpenTelemetry readable conventions' "$otel_root/docs"
    fi
  fi
fi

if [ "$found" -eq 0 ]; then
  exit 1
fi
