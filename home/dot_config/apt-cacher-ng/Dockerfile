# apt cache for Lima VMs; run by ~/.config/systemd/user/apt-cacher-ng.service.
FROM docker.io/debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

RUN apt-get update \
 && apt-get install -y --no-install-recommends apt-cacher-ng \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 3142
CMD ["/usr/sbin/apt-cacher-ng", "-c", "/etc/apt-cacher-ng", "ForeGround=1"]
