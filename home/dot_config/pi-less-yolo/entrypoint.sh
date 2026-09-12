#!/bin/sh
set -e

# Register the runtime UID in /etc/passwd before starting pi.
# SSH calls getpwuid(3) and hard-fails without an entry; nss_wrapper is
# unavailable in Wolfi so we append directly.
if ! grep -q "^[^:]*:[^:]*:$(id -u):" /etc/passwd; then
    printf 'piuser:x:%d:%d:piuser:%s:/bin/sh\n' \
        "$(id -u)" "$(id -g)" "${HOME}" >> /etc/passwd
fi

# Egress TLS interception (PI_EGRESS + secrets/inspect): trust the proxy CA.
# Node uses the additive NODE_EXTRA_CA_CERTS (set by _docker_flags); curl,
# git, and python replace their trust store via these vars, so hand them a
# combined bundle of the system CAs plus the proxy CA.
if [ -n "${PI_EGRESS_CA:-}" ] && [ -f "${PI_EGRESS_CA}" ]; then
    cat /etc/ssl/certs/ca-certificates.crt "${PI_EGRESS_CA}" > /tmp/pi-egress-ca-bundle.pem
    export SSL_CERT_FILE=/tmp/pi-egress-ca-bundle.pem
    export CURL_CA_BUNDLE=/tmp/pi-egress-ca-bundle.pem
    export REQUESTS_CA_BUNDLE=/tmp/pi-egress-ca-bundle.pem
    export GIT_SSL_CAINFO=/tmp/pi-egress-ca-bundle.pem
fi

# Pass through to a shell when invoked via `pi:shell`; otherwise run pi.
case "${1:-}" in
    bash|sh) exec "$@" ;;
    *) exec pi "$@" ;;
esac
