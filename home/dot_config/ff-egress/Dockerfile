FROM docker.io/debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS tunneldigger-build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates cmake git libnl-3-dev libnl-genl-3-dev pkg-config \
 && git clone https://github.com/wlanslovenija/tunneldigger.git /src \
 && git -C /src checkout 9a9a42741837115d99dd9c398a9a3976d81727d2 \
 && cmake -S /src/client -B /src/build -DUSE_LIBNL=TRUE -DCMAKE_C_FLAGS=-DHAVE_PTHREAD=1 \
 && cmake --build /src/build

FROM docker.io/debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

RUN apt-get update \
 && apt-get install -y --no-install-recommends batctl ca-certificates curl fastd iproute2 iputils-ping jq nftables rtorrent signify-openbsd udhcpc wireguard-tools \
 && rm -rf /var/lib/apt/lists/*

COPY profiles /profiles
COPY --from=tunneldigger-build /src/build/tunneldigger /usr/local/bin/
COPY entrypoint.sh parker-entrypoint.sh tunneldigger-entrypoint.sh udhcpc-script /usr/local/bin/

CMD ["bash"]
