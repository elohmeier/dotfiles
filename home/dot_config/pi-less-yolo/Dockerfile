# syntax=docker/dockerfile:1

# BASE_REGISTRY (PI_BASE_REGISTRY): swap just the registry, keeping the pin.
# docker.io/chainguard/* carries the same digests behind CloudFront, which
# helps where cgr.dev's presigned r2.cloudflarestorage.com blob redirects are
# answered with 403 by a corporate proxy.
# BASE_IMAGE (PI_BASE_IMAGE): replace the whole reference, for mirrors that
# lay the image out under a different path.
ARG BASE_REGISTRY=cgr.dev
ARG BASE_IMAGE=${BASE_REGISTRY}/chainguard/node:latest-dev@sha256:6dd22b58ad748bd8cf94e8f922388f0b3d78636d8105967077429a3944f9ed75
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

# APK_REPOSITORY (PI_APK_REPOSITORY): replace the image's apk repository.
# apk.cgr.dev serves APKINDEX inline but 303-redirects every package to a
# presigned r2.cloudflarestorage.com URL; where those are blocked, apk maps the
# 403 to EACCES and reports "Permission denied" for each package.
# https://packages.wolfi.dev/os carries the same builds and versions and serves
# them without a redirect, but is signed with the wolfi key rather than the
# chainguard keys the image trusts — so that key is mounted alongside.
ARG APK_REPOSITORY=""
RUN --mount=type=secret,id=apk_key \
    if [ -n "${APK_REPOSITORY}" ]; then \
      install -m 644 /run/secrets/apk_key /etc/apk/keys/wolfi-signing.rsa.pub \
      && echo "${APK_REPOSITORY}" > /etc/apk/repositories; \
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

# GITHUB_BASE_URL (PI_GITHUB_BASE_URL): base for GitHub release downloads. A
# mirror with the same <owner>/<repo>/releases/download/<tag>/<file> layout
# (e.g. Artifactory's generic-github-remote) works where github.com does not.
#
# uv is fetched here rather than with `mise install uv`: mise's release binaries
# are built with rustls, which rejects TLS-intercepting proxy certificates that
# carry a critical extension it does not recognise, and that rejection cannot be
# configured away. curl (OpenSSL) accepts them.
ARG UV_VERSION=0.12.9
ARG GITHUB_BASE_URL=https://github.com
RUN set -e \
&& triple="$(uname -m)-unknown-linux-gnu" \
&& url="${GITHUB_BASE_URL}/astral-sh/uv/releases/download/${UV_VERSION}/uv-${triple}.tar.gz" \
&& cd /tmp \
&& curl -fsSLO "${url}" \
&& curl -fsSLO "${url}.sha256" \
&& sha256sum -c "uv-${triple}.tar.gz.sha256" \
&& tar -xzf "uv-${triple}.tar.gz" -C /usr/local/bin --strip-components=1 \
     "uv-${triple}/uv" "uv-${triple}/uvx" \
&& rm "uv-${triple}.tar.gz" "uv-${triple}.tar.gz.sha256"

# uv picks up its extra trust roots from SSL_CERT_FILE (set above). Neither
# --system-certs nor the deprecated --native-tls changes that, and none of the
# three modes makes rustls accept a chain carrying a critical extension it does
# not recognise — an intercepting proxy that sends one stays unreachable for uv
# whatever is configured, so GITHUB_BASE_URL has to point somewhere it is not in
# the path. The mirror default matches uv's own and is inert unless overridden.
ENV UV_PYTHON_INSTALL_DIR=/usr/local/share/uv/python \
    UV_PYTHON_INSTALL_MIRROR=${GITHUB_BASE_URL}/astral-sh/python-build-standalone/releases/download

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
