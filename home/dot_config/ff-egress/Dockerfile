FROM docker.io/debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4 AS tunneldigger-build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates cmake git libnl-3-dev libnl-genl-3-dev pkg-config \
 && git clone https://github.com/wlanslovenija/tunneldigger.git /src \
 && git -C /src checkout 9a9a42741837115d99dd9c398a9a3976d81727d2 \
 && cmake -S /src/client -B /src/build -DUSE_LIBNL=TRUE -DCMAKE_C_FLAGS=-DHAVE_PTHREAD=1 \
 && cmake --build /src/build

FROM docker.io/debian:trixie-slim@sha256:f6b08b09a05725f9431502d3b5714f5c4576e82c1a84fa1debe0c24a7e0c3ec4

RUN apt-get update \
 && apt-get install -y --no-install-recommends batctl ca-certificates curl fastd iproute2 iputils-ping jq nftables rtorrent signify-openbsd udhcpc wireguard-tools \
 && rm -rf /var/lib/apt/lists/*

COPY profiles /profiles
COPY --from=tunneldigger-build /src/build/tunneldigger /usr/local/bin/
COPY entrypoint.sh parker-entrypoint.sh tunneldigger-entrypoint.sh udhcpc-script /usr/local/bin/

CMD ["bash"]
