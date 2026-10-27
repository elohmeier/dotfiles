---
name: n64
description: Set up, build, port, debug, and validate N64 homebrew using libdragon, Tiny3D, Pyrite64, Gopher64 capture, Ares validation, and M64/SummerCart64 hardware; inspect and embed ROM metadata. Not for gameplay help, commercial-ROM emulation, or generic artifact publishing.
---

# N64 Homebrew

Treat host tools, the guest ROM, emulators, and hardware as separate layers. Attribute every result to the layer actually tested.

Determine the target hardware profile from the project: original N64 with or without Expansion Pak, ModRetro M64, and the flashcart used (such as SummerCart64). Keep M64 and original-N64 evidence distinct.

Read only the relevant reference:

- [project-setup.md](references/project-setup.md) — layout, mise/uv environment, pinned SDK forks, toolchain images, and task contract; for new projects or requested setup changes
- [builds.md](references/builds.md) — toolchains, dependencies, frameworks, and ROM construction
- [rom-metadata.md](references/rom-metadata.md) — embedded descriptions, release information, homebrew header flags, versioning, artwork, and SummerCart menu compatibility
- [runtime.md](references/runtime.md) — memory, DMA, rendering, assets, audio, input, saves, and performance
- [testing.md](references/testing.md) — capture, debugging, emulators, and hardware

Preserve the project's installed, containerized, or vendored dependency boundary. After changing libdragon or Tiny3D, rebuild that dependency and the ROM; rebuilding Gopher64 cannot change guest code.

CPU caches are not coherent with DMA. Queued RSP/RDP inputs must remain valid until completion. Check the project's current SDK headers and examples instead of relying on remembered preview APIs.

Converted does not mean loaded or rendered. Capture throughput is not guest timing. Emulator success is not hardware qualification.

Do not redistribute Nintendo SDK code, ROM content, or derived commercial assets. Publishing ROMs to public or external locations and changing firmware, persistent hardware settings, saves, or connected devices require explicit authorization and exact targets.
