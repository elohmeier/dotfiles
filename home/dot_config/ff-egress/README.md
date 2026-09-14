# Freifunk egress container

Run the bundled Debian container through Freifunk. The current directory
is mounted at the same path and used as the working directory.

```sh
mise run ff                         # bash
mise run ff -- curl https://ifconfig.co
mise run ff -- rtorrent
mise run ff:status
mise run ff:stop
FF_PROFILE=ffbs mise run ff -- curl https://ifconfig.co
FF_PROFILE=ffnw mise run ff -- curl https://ifconfig.co
```

The workload has no capabilities and shares only the gateway's network
namespace. Its image contains `curl` and `rtorrent`. Images are never pulled by
the run task; build or pull them before starting the tunnel. To run a different
local image, set `FF_IMAGE`:

```sh
FF_IMAGE=alpine:latest mise run ff -- sh
```

`FF_PROFILE` selects a directory below `profiles/` and defaults to `ffhb`.
`ffbs` uses Freifunk Braunschweig's routed WireGuard/Parker network. Its
persistent identity is stored below `~/.local/state/ff-egress/ffbs`. Concentrator
3 is preferred based on measured throughput; override it with
`FF_CONCENTRATOR=1` or `FF_CONCENTRATOR=2` when starting a stopped gateway.
`ffnw` uses Nordwest's Bremen Tunneldigger/L2TP domain.

The Bremen profile requires `/dev/net/tun` and a loaded `batman_adv` module;
Braunschweig requires WireGuard. Check with `mise run ff:health` or
`FF_PROFILE=ffbs mise run ff:health`.
Nordwest additionally requires `l2tp_core`, `l2tp_netlink`, and `l2tp_eth`.
Load them with `sudo modprobe -a l2tp_core l2tp_netlink l2tp_eth`.
On rootless Podman, SELinux labeling is disabled only for the gateway container
so fastd can open `/dev/net/tun`; the unprivileged workload keeps its label.
