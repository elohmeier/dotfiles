#!/bin/bash
# Install Claude Code, Codex and pi globally via npm (pi needs Node >= 22.19, Debian 13 ships 20).
set -eux -o pipefail
claude --version && codex --version && pi --version && exit 0
export DEBIAN_FRONTEND=noninteractive
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
apt-get install -y nodejs
npm install --global --no-audit --no-fund @anthropic-ai/claude-code@latest @openai/codex@latest @earendil-works/pi-coding-agent@latest
node "$(npm root --global)/@anthropic-ai/claude-code/install.cjs"
claude --version && codex --version && pi --version
