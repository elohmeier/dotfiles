# apt cache for Lima VMs; run by ~/.config/systemd/user/apt-cacher-ng.service.
FROM docker.io/debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0

RUN apt-get update \
 && apt-get install -y --no-install-recommends apt-cacher-ng \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 3142
CMD ["/usr/sbin/apt-cacher-ng", "-c", "/etc/apt-cacher-ng", "ForeGround=1"]
