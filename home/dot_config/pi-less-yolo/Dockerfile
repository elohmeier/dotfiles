# syntax=docker/dockerfile:1

# BASE_IMAGE: set via PI_BASE_IMAGE to pull the base from a registry mirror.
ARG BASE_IMAGE=cgr.dev/chainguard/node:latest-dev@sha256:6dd22b58ad748bd8cf94e8f922388f0b3d78636d8105967077429a3944f9ed75
FROM ${BASE_IMAGE}

USER root

# Extra CA bundle for TLS-intercepting corporate proxies (built with
# PI_CA_CERT=/path/to/ca.pem). Runs before any download so apk/curl/npm/uv see
# it. No secret mounted -> no-op. Pointing NODE_EXTRA_CA_CERTS and
# SSL_CERT_FILE at the system bundle is a no-op too when nothing was appended:
# it is the same Mozilla root set Node and Python ship with.
ARG CA_ID=none
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then \
      echo "# pi-less-yolo extra CA ${CA_ID}" >> /etc/ssl/certs/ca-certificates.crt \
      && cat /run/secrets/extra_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi

# openssh-client: ssh binary for git-over-SSH (PI_SSH_AGENT=1) and ssh-add.
RUN apk add --no-cache \
        curl \
        ca-certificates \
        git \
        openssh-client \
        tmux

# Install mise (GPG-verified via mise-release.asc; secret mount avoids a rootless-Podman/SELinux AVC denial, #99).
RUN --mount=type=secret,id=mise_asc,target=/tmp/mise-release.asc,required=true \
set -e \
&& apk add --no-cache gpg gpg-agent \
&& gpg --import /tmp/mise-release.asc \
&& curl -fsSL https://mise.jdx.dev/install.sh.sig -o /tmp/mise-install.sh.sig \
&& gpg --decrypt /tmp/mise-install.sh.sig > /tmp/mise-install.sh \
&& MISE_VERSION=2026.9.1 MISE_INSTALL_PATH=/usr/local/bin/mise sh /tmp/mise-install.sh \
&& rm /tmp/mise-install.sh.sig /tmp/mise-install.sh \
&& apk del gpg gpg-agent

# ARG (not ENV): available during build, not baked in. At runtime mise defaults
# to ~/.local/share/mise, which the container user can write to.
ARG MISE_DATA_DIR=/usr/local/share/mise

# Install uv via mise and expose uv and uvx on PATH.
RUN set -e \
&& mise install uv@0.12.9 \
&& ln -s "$(mise exec uv@0.12.9 -- which uv)" /usr/local/bin/uv \
&& ln -s "$(mise exec uv@0.12.9 -- which uvx)" /usr/local/bin/uvx

ENV UV_PYTHON_INSTALL_DIR=/usr/local/share/uv/python

# Install Python via uv and expose it on PATH
RUN uv python install 3.14.7 \
    && ln -s "$(uv python find 3.14.7)" /usr/local/bin/python3

# Install pi globally
RUN npm install -g "@earendil-works/pi-coding-agent@0.85.1"

# Prepend extension binaries (host-mounted via /pi-agent). Security: binaries
# here can shadow any command; no privilege escalation (--cap-drop=ALL,
# --no-new-privileges), but review ~/.pi/agent/npm-global/bin/ after installs.
ENV PATH="/pi-agent/npm-global/bin:${PATH}"

# /home/piuser: world-writable (1777) so any runtime UID can write here.
# /home/piuser/.ssh: root-owned 755; SSH accepts it and the runtime user can
#   read mounts inside it (700 would block a non-matching UID).
# /etc/passwd: world-writable so the entrypoint can add the runtime UID.
#   SSH calls getpwuid(3) and hard-fails without a passwd entry. Safe here
#   because --cap-drop=ALL and --no-new-privileges block privilege escalation.
# .npmrc sets prefix=/pi-agent/npm-global so extensions persist across restarts.
# Written as a literal file because ENV HOME is not yet set to /home/piuser.
RUN mkdir -p /home/piuser /home/piuser/.ssh \
    && chmod 1777 /home/piuser \
    && chmod 755 /home/piuser/.ssh \
    && chmod a+w /etc/passwd \
    && touch /home/piuser/.ssh/known_hosts \
    && chmod 666 /home/piuser/.ssh/known_hosts \
    && echo "prefix=/pi-agent/npm-global" > /home/piuser/.npmrc

ENV HOME=/home/piuser

COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
