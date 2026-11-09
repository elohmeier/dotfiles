# apt cache for Lima VMs; run by ~/.config/systemd/user/apt-cacher-ng.service.
FROM docker.io/debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4

RUN apt-get update \
 && apt-get install -y --no-install-recommends apt-cacher-ng \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 3142
CMD ["/usr/sbin/apt-cacher-ng", "-c", "/etc/apt-cacher-ng", "ForeGround=1"]
