# Agent-specific mounts and environment; sourced after DOCKER_FLAGS is initialized.
export AGENT="${AGENT:-pi}"
case "${AGENT}" in
  pi)
    AGENT_HOME="${HOME}/.pi/agent"
    mkdir -p "${AGENT_HOME}"
    DOCKER_FLAGS+=(--volume "${AGENT_HOME}:/pi-agent" --env PI_CODING_AGENT_DIR=/pi-agent)
    ;;
  codex|claude)
    AGENT_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}/agent-sandbox/${AGENT}"
    mkdir -p "${AGENT_HOME}/.ssh"
    chmod 700 "${AGENT_HOME}"
    DOCKER_FLAGS+=(--volume "${AGENT_HOME}:/home/piuser")
    if [[ "${AGENT}" == codex ]]; then
      mkdir -p "${AGENT_HOME}/.codex"
      DOCKER_FLAGS+=(--env CODEX_HOME=/home/piuser/.codex)
    else
      DOCKER_FLAGS+=(--env CLAUDE_CONFIG_DIR=/home/piuser/.claude
        --env DISABLE_AUTOUPDATER=1 --env CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1)
    fi
    ;;
  *) echo "error: AGENT must be pi, codex, or claude" >&2; exit 1 ;;
esac
