# Recommended Project Setup

Use this baseline when creating an N64 project or when asked to standardize an existing one. Preserve existing layouts and entry points during unrelated work; directory renames, packaging scripts as a CLI, and merging SDK branches are separate choices.

## Inspect Before Changing

Fork branches maintained for different projects may share a base but diverge. One branch is not a superset of another; compare history before selecting fixes.

A lockfile or image label only helps when the executed workflow enforces it. Inspect setup tasks, dependency manifests, `.gitmodules`, Dockerfiles, and build entry points together.

## Ownership and Layout

mise owns host tool versions, environment defaults, developer tasks, and uv venv creation. uv synchronizes `.venv` from its lockfile. The build system owns compilation: libdragon Make for N64, Make or CMake/Ninja for native code. A project toolchain container provides the pinned MIPS compiler, libdragon, and optional Tiny3D.

Create only the parts the project uses:

```text
mise.toml, mise.lock          host tools and defaults
pyproject.toml, uv.lock       Python dependencies and resolution
mise-tasks/                   executable developer entry points
src/<host_package>/           packaged Python tools, if needed
n64/Makefile, n64/src/        target compilation and runtime
third_party/libdragon/        SDK submodule
third_party/<engine>/         optional pinned engine or reference dependency
docker/toolchain/Dockerfile   compiler base plus SDK installation
tests/                        synthetic host/converter/native fixtures
build/                        ignored generated assets, objects, source snapshots
dist/                         ignored ROMs, symbols, manifests
artifacts/                    ignored local test/capture evidence
```

Existing `vendor/`, `.mise-tasks/`, `runtime/`, or `platforms/n64/` are equally workable. A mature project CLI can own domain workflows; keep mise wrappers thin and avoid duplicating its logic in Make or shell.

Keep machine paths and personal overrides in ignored `mise.local.toml` or documented environment variables. Treat the container engine as an overridable command (`DOCKER`) and verify Docker/Podman mount and user behavior. When host tools need many system libraries, centralize image, mount, workdir, and UID/GID handling in one wrapper. Separate networked dependency acquisition from compilation; offline builds expose undeclared downloads. Keep emulator/GPU execution at its established boundary.

## Host Tools and Python

Any project using Python, even standard-library-only scripts, gets a mise-managed uv venv: a root `pyproject.toml` and committed `uv.lock` give a consistent setup/run contract without a build backend. If Python also runs inside a container, declare compatible versions for both and do not reuse the host `.venv` there.

Commit `mise.lock` with resolutions for supported platforms. `mise.lock` pins host tools; `uv.lock` pins Python packages; neither replaces the other. See [mise lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html).

Example `mise.toml` (versions illustrative):

```toml
min_version = "2026.9.1"

[tools]
python = "3.14.6"
uv = "0.12.6"

[settings]
python.uv_venv_auto = "create|source"

[env]
UV_PYTHON = { value = "{{ tools.python.path }}", tools = true }
DOCKER = "{{ env.DOCKER | default(value='docker') }}"
```

`python.uv_venv_auto` creates and activates `.venv` but requires a committed `uv.lock` and does not install packages; run `uv sync --locked` in setup. Do not also configure `_.python.venv`. See [mise Python integration](https://mise.jdx.dev/lang/python.html#automatic-virtualenv-activation).

Put runtime dependencies in `pyproject.toml` with a dev group for pytest/linters. A packaged CLI declares a build backend and console entry point. Keep `requires-python` and any `.python-version` aligned with mise. Avoid a parallel `PYTHONPATH` mechanism.

Routine task bodies use `uv run --locked ...`: bare `uv run` may update the lockfile, `--frozen` skips the metadata agreement check, and `uv pip install` bypasses the lock workflow. See [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/). Add Node with `npm ci` only when actual tools need it.

Example `mise-tasks/setup`:

```bash
#!/usr/bin/env bash
#MISE description="Synchronize locked host dependencies"
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
uv sync --locked
```

Pick one task directory and document `mise run` as the entry point; executing a task file directly bypasses mise's environment and dependencies. See [mise file tasks](https://mise.jdx.dev/tasks/file-tasks.html).

## SDK Forks and Branch Tracking

When building the SDK from source, pin libdragon as a Git submodule: upstream when it suffices, a maintained fork branch when fixes are required. Keep reusable SDK changes in the SDK repository and game-specific integration in the project. Tiny3D can be a submodule or a full commit pinned in the Dockerfile, provided library, microcode, and importer are built together.

Record a fork's clone URL and branch in `.gitmodules`:

```gitconfig
[submodule "third_party/libdragon"]
    path = third_party/libdragon
    url = https://github.com/<owner>/libdragon.git
    branch = mygame-fixes
```

The branch must exist and contain the selected commit. Use a clone URL collaborators can fetch; push URLs and `upstream` remotes are local configuration.

The parent's **gitlink commit** is the build pin. `branch` only selects the source for `git submodule update --remote`; detached HEAD after checkout is expected. See [Git submodule semantics](https://git-scm.com/docs/git-submodule). Bootstrap with `git submodule update --init --recursive`; after a clone-URL change, run `git submodule sync --recursive`. Keep branch-tip updates out of setup, toolchain builds, and CI.

For an intentional dependency update:

1. Inspect fork/upstream history and preserve local SDK work.
2. Select a reviewed commit, or evaluate the branch tip with `git submodule update --remote --checkout -- third_party/libdragon`. Review the diff and initialize changed nested submodules.
3. Develop SDK fixes on a named branch or worktree. Before sharing a parent revision, ensure its SDK commit is fetchable from the configured remote; if publishing is not authorized, report the local dependency.
4. Stage the gitlink, rebuild the SDK image and ROM, run the target gates, then commit.

A shared fork integration branch suits fixes several projects need; each project still pins its own tested commit. Do not assume another game's newer branch is safe.

For narrow engine patches, archive pinned sources into `build/`, apply a committed patch with conflicts as failures, and key the cache on source commit plus patch hash. Source transformations should validate expected context and record inputs and outputs. Object caches must account for generated sources, headers, flags, variant, and toolchain identity. A patched host reference must be identified as patched.

For small third-party libraries, release archives work: record URL, version, hash, and layout in a manifest and verify both downloads and cached archives. An archive checksum does not verify an already-extracted directory.

## Toolchain Contract

When building the SDK from source, pin the compiler base image by digest independently of the SDK gitlink. Build libdragon and host tools from the selected source, then Tiny3D, then the ROM; a base image's bundled SDK does not replace the selected source. See [builds.md](builds.md).

When consuming an existing SDK image, its installed headers, libraries, and tools are the compatibility boundary. A local image ID check does not make the image obtainable on a fresh machine: document a source recipe, a registry digest, or a verified image archive. Local image IDs and registry manifest digests identify different objects. Do not substitute another project's latest tag. See [Docker image pinning](https://docs.docker.com/build/building/best-practices/#pin-base-image-versions).

Record the final derived image too; added apt packages change it. Declare SDK source files used outside the image as dependencies rather than reading an undocumented sibling checkout.

A from-source builder should:

1. Require initialized submodules, a clean SDK, and SDK HEAD matching the parent gitlink. Accept the `.git` file form. Apply the same checks to nested dependencies.
2. Stage a temporary source archive with cleanup on failure. `git archive HEAD` omits dirty files and submodule contents; stage nested dependencies explicitly. Never label a dirty copy with its clean SHA; dirty experiments need an explicitly recorded snapshot (see [builds.md](builds.md)).
3. Record full dependency SHAs and the base digest; invalidate on SDK source or recipe changes. If a provenance file repeats gitlink/Dockerfile data, check agreement.
4. Before conversion or compilation, verify the image matches the selected revisions and recipe, e.g. via a fingerprint over Dockerfile, build arguments, platform, and dependency commits. Labels alone miss base or Dockerfile changes.
5. Resolve the image tag to its immutable ID for the run and record it, plus any registry digest.

Invalidate generated assets when converter inputs or toolchain identity change, and rebuild objects when SDK libraries or variants change; an image tag is not a Make prerequisite by itself. Preserve ELF/map files and write build evidence: parent revision and dirty state, dependency SHAs, image identity, asset/patch hashes, and ROM SHA-256. Pins improve repeatability; they do not prove bit-identical builds.

For code tied to SDK internals, targeted installed-file hash checks before compiling dependent objects are worthwhile. On mismatch, review compatibility and rebuild; do not just refresh the hashes.

## Developer Contract

Expose these tasks as needed:

| Task                | Contract                                                                        |
| ------------------- | ------------------------------------------------------------------------------- |
| `setup`             | Synchronize locked host dependencies; never advance SDK refs                    |
| `doctor`            | Report prerequisites, SDK state, and image compatibility; no repair or installs |
| `toolchain`         | Build the container from selected, verified inputs                              |
| `fetch-deps`        | Acquire and verify declared source archives before offline builds               |
| `assets`            | Convert declared source inputs incrementally                                    |
| `rom`               | Stage required assets, compile/link, and structurally check ROM                 |
| `check`             | Host tests, lint, and native runtime checks supported by available fixtures     |
| `smoke` / `capture` | Run the selected ROM in the emulator and record evidence                        |

Keep host checks usable without proprietary media or hardware. CI runs the same entry points and rejects stale locks, SDK/image mismatches, and structural ROM failures; claim only the emulator or hardware gates actually run. Keep publishing and device deployment out of automatic build dependencies.

Fresh-clone path:

```sh
git submodule update --init --recursive
mise trust
mise install
mise run setup
mise run toolchain
mise run doctor
mise run check
mise run rom
```

Update lockfiles through explicit dependency updates, not setup. Commit tool/dependency locks, `.gitmodules`, gitlinks, and build recipes; ignore `.venv/`, caches, generated files, local configuration, private media, and evidence.

When adopting incrementally: first the managed uv venv and lock-honoring installs, then pinned and verified SDK/image inputs, then consistent entry points.
