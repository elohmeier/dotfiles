# Builds

Read this for toolchain boundaries, dependency provenance, framework integration, or ROM construction.

For a new project or a requested setup migration, read [project-setup.md](project-setup.md). It recommends mise-managed uv venvs for Python tooling and explicit SDK source/image pins. It also covers consuming an existing SDK image and containerized native builds. Existing builds retain their current boundary unless changing it is part of the task.

## Preserve the Compatibility Boundary

Identify the project's build model before changing it:

| Signal                       | Preserve                                               |
| ---------------------------- | ------------------------------------------------------ |
| `$(N64_INST)/include/n64.mk` | Installed libdragon headers, libraries, and tools      |
| Local `t3d.mk`               | That Tiny3D checkout and its importer/microcode        |
| Repository container files   | Image inputs, arguments, mounts, and tag/digest        |
| Git submodules               | Recorded gitlinks and recursive dependency graph       |
| Custom CMake/linker/assets   | Existing compiler, ABI, linker script, and generators  |
| Pyrite64 project             | Editor/runtime revisions and generated-source boundary |

Do not replace one model with another as a build fix. Read the exact `n64.mk`, headers, libraries, and tools selected by the project.

For libdragon builds:

- Set `LIBDRAGON_PREVIEW` before including `n64.mk`; preserve the project's level.
- Use cross-tool variables exported by `n64.mk`.
- Separate object directories when compile-time variants differ.
- Make generated headers and assets explicit prerequisites.
- Preserve the ELF and map/symbol files for inspection and debugging.
- Keep ROM metadata consistent with runtime region, controller, save, RTC, and memory behavior.

For descriptive metadata, release versions, or SummerCart menu presentation, read [rom-metadata.md](rom-metadata.md). It covers embedding and sidecars, the header version byte's save/RTC meaning, and the fields the menu actually displays.

Tiny3D headers, library, RSP microcode, `gltf_to_t3d`, and model format must come from compatible revisions. Do not mix an installed component with an unrelated checkout. For Pyrite64, edit the editor/scene source of truth rather than generated output unless the repository says otherwise.

## Containers and Local Dependencies

For project submodules, use the recorded commits; never use `git submodule update --remote` for a reproducible build. Record relevant commits, dirty state, base image digest, and final toolchain image digest.

Docker cannot copy an arbitrary checkout outside its context. If a project consumes local SDK work, stage an ignored snapshot and record its provenance. `git archive HEAD` omits dirty changes and submodule contents; use an explicit marked-dirty snapshot when those changes matter.

Install in dependency order: libdragon and host tools, matching Tiny3D and importer, then higher-level runtimes. Assert required outputs under `N64_INST`. A changed staged source must invalidate the corresponding image layer.

After changing libdragon or Tiny3D:

1. Rebuild the exact installed dependency or toolchain image.
2. Verify its recorded revision and dirty state.
3. Rebuild the ROM and confirm its hash changed for the expected reason.
4. Run the smallest relevant target gate.

Reinstalling Gopher64 is not part of this chain.

## Inspect the Artifact

A normal big-endian z64 ROM begins with `80 37 12 40`:

```sh
test -s build/game.z64
test "$(od -An -tx1 -N4 build/game.z64 | tr -d ' \n')" = 80371240
sha256sum build/game.z64
```

Run size, symbol, and disassembly tools from the same cross-toolchain environment that built the ELF. ROM capacity is not RDRAM capacity; embedded files, compression, padding, and metadata can grow the ROM without changing resident memory in the same way.

Common provenance failures are mismatched Tiny3D components, stale variant objects, generated assets missing from the ROM filesystem, preview APIs used with the wrong header revision, and a rebuilt emulator paired with an unchanged guest ROM.
