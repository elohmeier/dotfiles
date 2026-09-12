# syntax=docker/dockerfile:1

FROM docker.io/mitmproxy/mitmproxy:latest@sha256:00b77b5d8804c8ad18cb6caefbf9d5849e895e8986c5ce011f4ae30f4385962f

COPY pi_egress.py /addons/pi_egress.py

# mitmproxy resolves paths through HOME in a few places; /tmp is writable for
# any --user UID. The policy/CA state lives in /egress (host-mounted).
ENV HOME=/tmp

EXPOSE 3128

# The base image's entrypoint assumes it starts as root and drops privileges
# via gosu; we always run with --user, so invoke mitmdump directly.
#   confdir=/egress/mitmproxy      persists the generated CA across restarts
#   connection_strategy=lazy       no DNS lookup or upstream connection for
#                                  hosts the addon rejects at CONNECT time
ENTRYPOINT ["mitmdump", \
  "--listen-port", "3128", \
  "--set", "confdir=/egress/mitmproxy", \
  "--set", "connection_strategy=lazy", \
  "-s", "/addons/pi_egress.py"]
