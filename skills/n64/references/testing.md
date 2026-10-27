# Testing

Read this for emulator automation, capture, crash diagnosis, independent validation, M64, or SummerCart64.

## Evidence

Move through only the gates needed for the claim:

1. Host converter or pure-logic tests
2. Native shared-code simulation or deterministic replay
3. ROM header, hash, size, and filesystem validation
4. Gopher64 boot, structured guest markers, and capture
5. An independent accurate emulator such as Ares
6. M64 with SummerCart64
7. Original Nintendo 64 when its behavior matters

State the highest gate reached. M64 and original-N64 results are different evidence.

Use stable, project-prefixed, newline-terminated guest markers such as `GAME BOOT_OK`, `GAME RENDER_OK`, or `GAME SCENARIO_OK id=...`. Emit success only after the named condition. Log caps, fallbacks, and recovery explicitly. Development ROMs using libdragon emulator logging must not compile that logging out.

Use precise claims: converted, loads, renders, named scenario passes, emulator-qualified, M64-qualified, or original-N64-qualified. Avoid broader words such as complete, playable, or hardware-ready unless the project defines and exercises them.

## Gopher64 Capture

Use the Gopher64 binary the project selects; capture may require a build with capture support. Probe its version and capture options at runtime; confirm FFmpeg/FFprobe when media is required. Keep capture recipes, replay inputs, marker assertions, guest timing gates, and media validation in the project.

Marker-gated capture should have:

- A render-ready start marker rather than a guessed boot delay
- Bounded marker time in emulated seconds and a separate wall timeout
- Unique log, video, temporary, and emulator-state paths per concurrent job
- Structured crash/failure matching instead of rejecting generic words
- Stream, dimensions, duration, frame, and representative-image checks

Capture acceleration removes realtime pacing and records VI/AI output. Its realtime multiplier, readback, and encoder timings measure host throughput, not guest frame time. Publish only validated files through the generic publishing workflow; publication does not strengthen the N64 evidence.

## Ares

Ares serves as the independent validation emulator (gate 5). A source checkout is separate evidence from the installed binary; probe and record `--version` before claiming an Ares result. Load N64 ROMs with `ares --system "Nintendo 64" game.z64`; `--dump-all-settings` lists `Nintendo64/*` options settable via `--setting name=value`. Ares is a GUI emulator that needs a display and has no headless, marker, or scripted-capture interface — keep automated marker-gated runs on Gopher64 and use Ares for interactive cross-checks and emulator-disagreement diagnosis.

## Diagnosis

Preserve the failing ROM, ELF, symbols/map, full log, emulator version, dependency revisions, replay inputs, and last successful marker.

| Symptom                       | First boundary to inspect                                      |
| ----------------------------- | -------------------------------------------------------------- |
| No boot marker                | Header, toolchain, startup, early exception                    |
| Boot but no filesystem marker | ROM filesystem, paths, format, DMA                             |
| Render marker timeout         | Frame lifecycle, queues, missing asset, deadlock               |
| Failure disappears with waits | Lifetime, ownership, cache, race                               |
| Emulator disagreement         | Undefined behavior, DMA/cache, timing, emulator implementation |
| Hardware-only failure         | Alignment, timing, cart, memory, region, controller, firmware  |

Use assertions, symbolized backtraces, RDPQ validation, focused RDP logs, or RSP diagnostics as appropriate. Use the ELF—not the z64—with an N64-capable MIPS GDB. Remove broad diagnostic waits after fixing the cause.

## M64 and SummerCart64

Use an accuracy/default timing mode for baselines and record the ROM checksum, M64 firmware/mode, video and region behavior, controller, and SummerCart firmware/deployer. HDMI output mode is not the guest VI mode. Do not infer original-hardware behavior from the FPGA implementation.

Before uploading, obtain explicit authorization, resolve one device and ROM, validate z64 magic/checksum/size and required metadata, and fail closed if device selection is absent or ambiguous. Keep upload, reset, save writeback, persistent settings, and firmware operations distinct.

Never update M64 or SummerCart64 firmware as a troubleshooting side effect. Firmware changes require a separate explicit request, compatibility verification, and a recovery plan.
