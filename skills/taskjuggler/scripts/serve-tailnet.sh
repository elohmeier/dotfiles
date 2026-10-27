#!/usr/bin/env bash
set -euo pipefail

script_name="${0##*/}"
allow_existing=false
build_only=false
dry_run=false
output_dir=""
https_port=443
serve_path="/"
use_sudo=false
project=""

usage() {
  cat <<EOF
Usage: $script_name [options] PROJECT.tjp

Validate and build TaskJuggler HTML reports, then serve them privately over
Tailscale HTTPS.

Options:
  --allow-existing      Permit changes when the node already has Serve mappings
  --build-only          Build reports without changing Tailscale configuration
  --dry-run             Build, check Serve state, and print the publish command
  -o, --output-dir DIR  Output directory (default: PROJECT_DIR/build/reports)
  --https-port PORT     Tailscale HTTPS port (default: 443)
  --set-path PATH       URL mount path (default: /)
  --sudo                Use sudo for the Tailscale command only
  -h, --help            Show this help
EOF
}

die() {
  echo "$script_name: $*" >&2
  exit 1
}

require_value() {
  local option="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || die "$option requires a value"
}

while (($# > 0)); do
  case "$1" in
    --allow-existing)
      allow_existing=true
      shift
      ;;
    --build-only)
      build_only=true
      shift
      ;;
    --dry-run)
      dry_run=true
      shift
      ;;
    -o | --output-dir)
      require_value "$1" "${2:-}"
      output_dir="$2"
      shift 2
      ;;
    --https-port)
      require_value "$1" "${2:-}"
      https_port="$2"
      shift 2
      ;;
    --set-path)
      require_value "$1" "${2:-}"
      serve_path="$2"
      shift 2
      ;;
    --sudo)
      use_sudo=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      [[ -z "$project" ]] || die "only one project file may be specified"
      project="$1"
      shift
      ;;
  esac
done

if (($# > 0)); then
  [[ -z "$project" && $# -eq 1 ]] || die "only one project file may be specified"
  project="$1"
fi

[[ -n "$project" ]] || {
  usage >&2
  exit 2
}
[[ "$build_only" == false || "$dry_run" == false ]] || die "--build-only and --dry-run cannot be combined"
[[ -f "$project" ]] || die "project not found: $project"
[[ "$https_port" =~ ^[0-9]+$ ]] || die "HTTPS port must be an integer"
((https_port >= 1 && https_port <= 65535)) || die "HTTPS port must be between 1 and 65535"
[[ "$serve_path" == /* ]] || die "Serve path must begin with /"
command -v tj3 >/dev/null 2>&1 || die "tj3 is required"

project_path="$(realpath "$project")"
project_dir="${project_path%/*}"
project_name="${project_path##*/}"

if [[ -z "$output_dir" ]]; then
  output_dir="$project_dir/build/reports"
elif [[ "$output_dir" != /* ]]; then
  output_dir="$PWD/$output_dir"
fi

mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd -P)"

echo "Validating $project_path"
(
  cd "$project_dir"
  tj3 --silent --check-syntax "$project_name"
  tj3 --silent --no-reports "$project_name"
)

report_list="$(
  cd "$project_dir"
  tj3 --silent --no-reports --list-reports '.*' "$project_name"
)"
printf '%s\n' "$report_list"

html_declared=false
while IFS=$'\t' read -r _ formats _; do
  if [[ ",$formats," == *,html,* ]]; then
    html_declared=true
    break
  fi
done <<<"$report_list"
[[ "$html_declared" == true ]] || die "project does not declare an HTML report"

echo "Generating reports in $output_dir"
(
  cd "$project_dir"
  tj3 --silent --output-dir "$output_dir" "$project_name"
)

html_file="$(find "$output_dir" -type f -name '*.html' -print -quit)"
[[ -n "$html_file" ]] || die "TaskJuggler completed without generating an HTML file"
echo "Report site ready: $output_dir"

if [[ "$build_only" == true ]]; then
  exit 0
fi

command -v tailscale >/dev/null 2>&1 || die "tailscale is required unless --build-only is used"

status_command=(tailscale serve status --json)
if [[ "$use_sudo" == true ]]; then
  command -v sudo >/dev/null 2>&1 || die "sudo is not available"
  status_command=(sudo "${status_command[@]}")
fi

serve_status="$("${status_command[@]}")"
compact_status="${serve_status//$'\n'/}"
compact_status="${compact_status//$'\r'/}"
compact_status="${compact_status//$'\t'/}"
compact_status="${compact_status// /}"
if [[ "$compact_status" != "{}" && "$allow_existing" == false ]]; then
  printf '%s\n' "$serve_status" >&2
  die "Serve mappings already exist; inspect them and rerun with --allow-existing if this change should coexist"
fi

serve_command=(tailscale serve --bg "--https=$https_port")
disable_command=(tailscale serve "--https=$https_port")
if [[ "$serve_path" != "/" ]]; then
  serve_command+=("--set-path=$serve_path")
  disable_command+=("--set-path=$serve_path")
fi
serve_command+=("$output_dir")
disable_command+=(off)

if [[ "$use_sudo" == true ]]; then
  serve_command=(sudo "${serve_command[@]}")
  disable_command=(sudo "${disable_command[@]}")
fi

if [[ "$dry_run" == true ]]; then
  echo "Would configure Tailscale Serve with:"
  printf '  '
  printf '%q ' "${serve_command[@]}"
  printf '\n'
  exit 0
fi

"${serve_command[@]}"

echo "Disable this mapping with:"
printf '  '
printf '%q ' "${disable_command[@]}"
printf '\n'
