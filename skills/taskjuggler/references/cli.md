# TaskJuggler CLI Guide

## Contents

- [Install and verify the personal fork](#install-and-verify-the-personal-fork)
- [`tj3`: parse, schedule, report](#tj3-parse-schedule-report)
- [`tj3man`: installed syntax reference](#tj3man-installed-syntax-reference)
- [Daemon, client, and web server](#daemon-client-and-web-server)
- [Private HTTPS with Tailscale Serve](#private-https-with-tailscale-serve)
- [Time/status sheet tools](#timestatus-sheet-tools)
- [Configuration and safety](#configuration-and-safety)
- [Diagnostics and exit behavior](#diagnostics-and-exit-behavior)

## Install and Verify the Personal Fork

Prefer the maintained `elohmeier/tap/taskjuggler` formula when the task calls
for the personal Ruby-compatible build. The formula pins an immutable revision
of [elohmeier/TaskJuggler](https://github.com/elohmeier/TaskJuggler) and uses a
platform bottle when one is available.

```bash
brew tap elohmeier/tap
brew install elohmeier/tap/taskjuggler

# For an existing installation.
brew update
brew upgrade elohmeier/tap/taskjuggler
```

Do not install or upgrade packages during a read-only diagnosis. When
provenance matters, inspect the active formula instead of relying on a copied
version or commit:

```bash
brew info elohmeier/tap/taskjuggler
brew cat elohmeier/tap/taskjuggler
tj3 --version
```

Do not silently substitute the RubyGems.org artifact for the personal build;
confirm that it contains the required compatibility fixes first.

## `tj3`: Parse, Schedule, Report

`tj3 [options] <main.tjp> [additional.tji ...]` performs three conceptual phases: parse all input, schedule/check all active scenarios, then generate reports.

### Inspection

```bash
tj3 --version
tj3 --help
```

### Staged validation

```bash
# Parse and macro/include validation only.
tj3 --silent --check-syntax project.tjp

# Parse, schedule, and consistency checks without report writes.
tj3 --silent --no-reports project.tjp

# Treat warnings as failures in CI or strict review.
tj3 --silent --abort-on-warnings --no-reports project.tjp

# Schedule, then list report ID, formats, and output name.
tj3 --silent --no-reports --list-reports '.*' project.tjp
```

Do not stop at `--check-syntax`; resource contention, dependency loops, missing scheduling criteria, and constraint failures emerge during scheduling.

### Report selection

```bash
# Exact ID; repeat --report for several IDs.
tj3 --output-dir build/reports --report overview project.tjp

# IDs matching a regular expression; repeat --reports as needed.
tj3 --output-dir build/reports --reports '^public\.' project.tjp

# Inspect a subset of declared reports without generating them.
tj3 --no-reports --list-reports '^public\.' project.tjp

# Generate the complete declared report set into an existing directory.
tj3 --output-dir build/reports project.tjp
```

The output directory passed to `-o`/`--output-dir` must already exist. It applies to the complete report set as well as reports selected with `--report` or `--reports`; generated reports and their HTML support assets are written below that directory. Inspect `git status` before and after report generation when working in a repository.

Other notable options:

| Option                          | Effect                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------ |
| `-c N`                          | Use up to N CPU cores for scheduling/report work                                     |
| `--silent`                      | Suppress banner/progress; warnings and errors remain                                 |
| `--no-color`                    | Disable terminal ANSI color                                                          |
| `--abort-on-warnings`           | Return failure behavior for warnings as for errors                                   |
| `--force-reports`               | Generate despite schedule errors; use only for diagnosis and label output unreliable |
| `--add-trace`                   | Append a snapshot to every trace report; mutates trace CSV data                      |
| `--check-time-sheet file.tji`   | Validate a time sheet against the loaded project                                     |
| `--check-status-sheet file.tji` | Validate a status sheet against the loaded project                                   |
| `--warn-ts-deltas`              | Warn about requested time-sheet changes                                              |

### Freeze historical assignments

```bash
tj3 --freeze --freezedate 2026-07-31 project.tjp
tj3 --freeze --freezebytask --freezedate 2026-07-31 project.tjp
```

Freeze requires a `trackingscenario`. It generates or rewrites `<base>-header.tji` and `<base>-bookings.tji` in the current working directory; the latter is grouped by resource unless `--freezebytask` is used. Include both files at the documented positions and review their diffs. Freeze continues through normal report generation unless report selection suppresses unrelated outputs.

## `tj3man`: Installed Syntax Reference

`tj3man` reads the same grammar metadata used to generate TaskJuggler's reference manual.

```bash
# List all keywords and context-qualified variants.
tj3man

# Explain syntax, arguments, valid contexts, inheritance, and related entries.
tj3man task
tj3man depends
tj3man include.properties
tj3man shift.task

# Generate the local HTML manual or open HTML help (browser-dependent).
tj3man --manual --dir build/manual
tj3man --html task
```

Prefer this installed, version-matched reference over remembered or third-party syntax. A plain keyword may report multiple matches; rerun with the shown qualified name.

## Daemon, Client, and Web Server

Use the server stack when repeated report requests should reuse scheduled projects. For ordinary local or CI builds, prefer `tj3` because it is simpler and avoids a long-lived service.

| Command     | Role                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| `tj3d`      | Load/schedule projects into resident processes and serve local DRb client requests (default port 8474) |
| `tj3client` | Add/update/remove projects, list/generate reports, and validate sheets through `tj3d`                  |
| `tj3webd`   | Serve dynamically generated HTML reports over HTTP (default port 8080) using `tj3d`                    |

Minimal trusted-local workflow:

```bash
tj3d --dont-daemonize --config taskjuggler.rc project.tjp
tj3client --config taskjuggler.rc status
tj3client --config taskjuggler.rc list-reports project_id
tj3client --config taskjuggler.rc report project_id overview
tj3client --config taskjuggler.rc terminate
```

Start the daemon in the foreground while diagnosing it. Once stable, omit `--dont-daemonize` and set a logfile.

Core client commands:

```text
status
terminate
add <tjp> [tji ...]
update
remove <project-id> [project-id ...]
list-reports <project-id> [report-id]
report <project-id> <report-id> [report-id ...] [= tji ...]
check-ts <project-id> <time-sheet>
check-ss <project-id> <status-sheet>
```

- Add `--regexp` when client report IDs are regular expressions.
- Repeat `--format html|csv|mspxml|niku|tjp` to override formats for a client report request.
- Additional `.tji` files after `=` supplement only that report-server request.
- Use `--port 0 --urifile <file>` consistently across daemon/client/webd to use an ephemeral daemon port.
- `tj3webd` exposes reports to hosts that can reach its HTTP listener. Do not use it for confidential reports on an untrusted network.

## Private HTTPS with Tailscale Serve

Use the bundled script to validate a project, generate all declared reports,
verify that HTML was produced, and optionally expose the output directory over
private tailnet HTTPS:

```bash
# Build and inspect without changing Tailscale configuration.
scripts/serve-tailnet.sh --build-only plan.tjp

# Build, inspect existing Serve state, and print the publish command.
scripts/serve-tailnet.sh --dry-run plan.tjp

# Build and configure a persistent HTTPS file server on the node.
scripts/serve-tailnet.sh plan.tjp

# Use sudo only for the Tailscale command when the current user is not an operator.
scripts/serve-tailnet.sh --sudo plan.tjp

# Mount alongside another root handler.
scripts/serve-tailnet.sh --set-path /schedule plan.tjp
```

The output directory defaults to `build/reports` beside the project. Override
it with `--output-dir`. The HTTPS port defaults to 443 and can be changed with
`--https-port`.

The background Serve configuration persists across Tailscale and machine
restarts. The script prints the matching disable command after publishing.
The script refuses to modify a node with existing Serve mappings unless
`--allow-existing` is passed after inspecting them.
Use Serve for tailnet-only access; never replace it with Funnel unless the user
explicitly requests public internet exposure.

## Time/Status Sheet Tools

These are configuration-heavy email/SCM workflows built on a running daemon:

| Command          | Purpose                                                                        |
| ---------------- | ------------------------------------------------------------------------------ |
| `tj3ts_sender`   | Generate and email time-sheet templates                                        |
| `tj3ts_receiver` | Read an email from stdin, validate the attached time sheet, file it, and reply |
| `tj3ts_summary`  | Send accepted individual sheets and/or digest summaries                        |
| `tj3ss_sender`   | Generate and email status-sheet templates for managers                         |
| `tj3ss_receiver` | Receive, validate, file, and acknowledge status sheets from stdin              |

Use each command's `--help` because date defaults depend on the current day. Start sender/receiver/summary setup with `--dryrun`, use `--directory` to pin the working tree, and verify mail, SCM, acceptable-interval, and daemon settings before permitting external effects.

## Configuration and Safety

All suite programs accept `--config <YAML-file>`. Without it, TaskJuggler searches the current directory, the user's home, and `/etc`, trying `.taskjugglerrc` then `taskjuggler.rc` in each directory.

Daemon/client communication needs a shared secret:

```yaml
_global:
  authKey: replace-with-a-long-random-secret
  _log:
    logLevel: 3
    outputLevel: 3
```

Quote YAML values when their type could be ambiguous. Keep real keys out of version control and process output. The daemon accepts only localhost DRb connections, but the implementation has not received a comprehensive security review; use it only among trusted local users. The web server has a broader HTTP exposure.

Do not use `tj3client --unsafe` in routine operation. It disables the report-generation sandbox and is intended for debugging/testing only.

## Diagnostics and Exit Behavior

- Successful commands return zero; parse, scheduling, report, connectivity, sheet, or option errors return nonzero.
- Warnings normally do not fail a run. Use `--abort-on-warnings` when warnings must break validation.
- `--silent` keeps output concise but does not suppress warnings/errors.
- Use `--no-color` when capturing stable logs.
- Diagnose in order: `tj3man` exact syntax, `--check-syntax`, `--no-reports`, `--list-reports`, one selected report, then the full report set.
- When a project behaves differently through `tj3client`, confirm working directory, config file, project ID, input/include paths, daemon reload state, and supplemental `.tji` files.
