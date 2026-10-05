#!/usr/bin/env bash
# Shared launcher, sourced by mise tasks.
set -euo pipefail

mode="$1"
shift
if [[ "${mode}" != shell ]]; then
  export AGENT="${mode}"
fi
export AGENT="${AGENT:-pi}"

# An explicitly empty PI_EGRESS disables filtering. Shells retain traffic capture.
PI_EGRESS="${PI_EGRESS-interactive}"
if [[ "${mode}" == shell ]]; then
  PI_EGRESS_RECORD="${PI_EGRESS_RECORD-1}"
  PI_EGRESS_INSPECT="${PI_EGRESS_INSPECT-all}"
fi
source "$(dirname "${BASH_SOURCE[0]}")/container.sh"

DOCKER_FLAGS+=("--interactive")
[[ ! -t 0 || ! -t 1 ]] || DOCKER_FLAGS+=("--tty")

prompt="You are running inside a container as a non-root user. No Docker socket, sudo, or system package installation is available."
if [[ -n "${PI_EGRESS:-}" ]]; then
  prompt+=" Outbound network access is filtered. If a host is blocked, tell the user; they can permit it with 'AGENT=${AGENT} mise run agent:egress allow <host>'. Scoped credential variables contain placeholders which the proxy replaces only for approved destinations."
fi
args=()
case "${mode}" in
  shell) args=(bash) ;;
  pi)
    args=(pi)
    [[ -n "${PI_NO_CONTAINER_PROMPT:-}" ]] || args+=(--append-system-prompt "${prompt}")
    if [[ -n "${TMUX:-}" ]]; then
      tmux set-option -p allow-passthrough on 2>/dev/null || true
      trap 'tmux set-option -p allow-passthrough off 2>/dev/null || true' EXIT
    fi
    ;;
  codex)
    # The container enforces isolation; no nested sandbox or host daemon.
    args=(codex --no-daemon --dangerously-bypass-approvals-and-sandbox
      -c 'cli_auth_credentials_store="file"')
    # Read the (possibly substituted) key at request time; never persist it in auth.json.
    if [[ -n "${OPENAI_API_KEY:-}" ]]; then
      args+=(-c 'model_provider="sandbox-openai"'
        -c 'model_providers.sandbox-openai={name="OpenAI",base_url="https://api.openai.com/v1",env_key="OPENAI_API_KEY",wire_api="responses"}')
    fi
    ;;
  claude) args=(claude --append-system-prompt "${prompt}") ;;
esac
"${DOCKER_CMD}" run "${DOCKER_FLAGS[@]}" "${PI_IMAGE}" "${args[@]}" "$@"
