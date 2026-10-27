# Runtime

Read this for target correctness, asset formats, rendering, audio, input, saves, determinism, or guest performance.

## Hardware Budgets

Determine whether the project requires 8 MiB RDRAM (Expansion Pak or M64). Treat 4 MiB support as a separate tested mode.

| Resource      | Constraint                                                                            |
| ------------- | ------------------------------------------------------------------------------------- |
| RDRAM         | Code, heap, stacks, frame/z buffers, queues, audio, and assets compete for 4 or 8 MiB |
| RSP IMEM/DMEM | 4 KiB each for microcode instructions and working data                                |
| RDP TMEM      | 4 KiB; formats, mipmaps, and TLUTs reduce usable layouts                              |
| CPU caches    | Small and software-managed around DMA                                                 |
| ROM           | Larger than RDRAM, but content still needs bounded loading and decoding               |

Measure static sections, heap high-water mark, stacks, surfaces, queues, audio, resident assets, scratch buffers, and worst transition peaks. Detect required Expansion Pak memory and fail clearly on smaller targets.

## Target Formats and DMA

The target is big-endian. Define binary formats with a magic, version, fixed-width fields, byte order, counts, offsets, and total length. Validate overflow and every range before allocation or access. Align data for its DMA and consumer contracts; change producer and guest consumer together.

The VR4300 data cache is not coherent with PI, RSP, or RDP DMA. Determine the producer, consumer, and ownership transition before adding cache operations:

- CPU to hardware: write modified cache data back before DMA reads it.
- Hardware to CPU: invalidate stale CPU cache data after completion.
- Do not reuse a buffer until asynchronous work completes.
- Respect the exact alignment and cache-line rules in current libdragon headers.

Prefer libdragon loaders and queue APIs that already implement the contract. Do not use raw cartridge access while PI DMA may be active.

## RSP, RDP, and Tiny3D

Submission is not completion. Keep queued matrices, vertices, models, textures, command blocks, and surfaces alive and coherent until their API releases ownership. Do not display a framebuffer still owned by rendering or render into one owned by VI.

Use a documented fence or wait to diagnose lifetime failures, then remove unnecessary serialization. A bug hidden by a global wait usually indicates ownership, cache, lifetime, or missing prerequisites.

Tiny3D specifics:

- Use the current `T3DVertPacked` definition and matching importer.
- Vertices and matrices referenced by queued commands or blocks must remain valid.
- UVs are pixel-based fixed-point values, not normalized OpenGL coordinates.
- Textures and material state use RDPQ/libdragon rather than a generic texture object.
- Isolate export, glTF conversion, target load, transforms, culling, materials, and queue state when diagnosing models.

Choose texture formats and batching for TMEM rather than source dimensions. Quantize and validate geometry offline; record cap overflow. Partition large scenes for bounded residency and prove transition peaks. Keep collision simpler than render geometry when possible.

## Host/Target Split and Determinism

Precompute parsing, triangulation, quantization, texture/audio conversion, scene packing, and validation on the host. Keep target loading bounded.

Pure gameplay logic may share source with a native harness, but native success is not target integration. Exact host/VR4300 comparisons require defined arithmetic, fixed seeds and timesteps, explicit endianness/layout, and deliberate floating-point flags. Keep target-only rendering, DMA, audio, and timing in target gates.

## Audio, Input, Saves, and Performance

Include decode buffers and active voices in memory and RSP budgets. Avoid blocking bulk reads in the render path; test looping, transitions, underruns, clipping, and voice limits.

Test controller absence and port behavior, held versus pressed input, region timing, and the declared ROM metadata. Save metadata must match runtime calls; cover cold, existing, corrupt, full, and writeback cases.

Optimize measured guest bottlenecks. Separate CPU, RSP, RDP, DMA/loading, audio, and VI pacing. Record deterministic scenes, ROM hash, memory peaks, frame windows, and toolchain provenance. Emulator or encoder profiling explains host capture cost, not N64 hotspots. Record M64 overclocking separately from the default accuracy/timing baseline.

For commercial-derived assets, follow the owning project's legal and version-control boundary; never treat successful conversion as full-game qualification.
