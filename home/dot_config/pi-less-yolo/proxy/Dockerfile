# syntax=docker/dockerfile:1

FROM docker.io/mitmproxy/mitmproxy:latest@sha256:00b77b5d8804c8ad18cb6caefbf9d5849e895e8986c5ce011f4ae30f4385962f

# mitmproxy uses certifi, independently of the Pi image's system trust store.
# Preserve its public roots and append PI_CA_CERT for corporate upstreams.
ARG CA_ID=none
RUN --mount=type=secret,id=extra_ca \
    mkdir -p /etc/pi-egress \
    && cp "$(python -c 'import certifi; print(certifi.where())')" /etc/pi-egress/upstream-ca.pem \
    && if [ -s /run/secrets/extra_ca ]; then \
      printf '\n# pi-less-yolo extra CA %s\n' "${CA_ID}" >> /etc/pi-egress/upstream-ca.pem \
      && cat /run/secrets/extra_ca >> /etc/pi-egress/upstream-ca.pem; \
    fi

COPY *.py /addons/
COPY approvals.html approvals.js /addons/

# mitmproxy resolves paths through HOME in a few places; /tmp is writable for
# any --user UID. The policy/CA state lives in /egress (host-mounted).
ENV HOME=/tmp

EXPOSE 3128

# The base image's entrypoint assumes it starts as root and drops privileges
# via gosu; we always run with --user, so start our WebMaster directly.
#   confdir=/egress/mitmproxy      persists the generated CA across restarts
#   connection_strategy=lazy       no DNS lookup or upstream connection for
#                                  hosts the addon rejects at CONNECT time
ENTRYPOINT ["python", "-u", "/addons/pi_web.py", \
  "--listen-port", "3128", \
  "--set", "confdir=/egress/mitmproxy", \
  "--set", "ssl_verify_upstream_trusted_ca=/etc/pi-egress/upstream-ca.pem", \
  "--set", "connection_strategy=lazy"]
