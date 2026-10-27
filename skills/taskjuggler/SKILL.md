---
name: taskjuggler
description: Use when installing, creating, editing, explaining, debugging, validating, or running TaskJuggler projects, especially the elohmeier Homebrew build, .tjp/.tji files, task/resource/dependency schedules, effort/length/duration semantics, scenarios, reports, tj3/tj3man/tj3d/tj3client CLI workflows, or privately serving generated HTML reports with Tailscale Serve.
---

# TaskJuggler

Treat TaskJuggler as a project compiler: describe the work breakdown, resources, calendars, dependencies, and constraints in source files; let the scheduler compute dates and allocations; then generate explicitly declared reports.

## First Checks

1. Run `tj3 --version` and use the installed version's behavior. For the maintained personal build, verify `brew info elohmeier/tap/taskjuggler`; install or upgrade it only when the user authorizes package changes.
2. Locate existing project sources with `rg --files -g '*.tjp' -g '*.tji'`. Read the main `.tjp`, its includes, and relevant report definitions before editing.
3. Ask `tj3man <keyword>` for exact syntax. When a keyword has multiple meanings, use the context-qualified entry shown by `tj3man`, such as `include.project`, `include.properties`, or `shift.task`.
4. Load only the reference needed for the task:

   - Read [references/language.md](references/language.md) for file structure, scheduling semantics, inheritance, identifiers, time, resources, scenarios, reports, and tracking.
   - Read [references/cli.md](references/cli.md) for `tj3`, `tj3man`, daemon/client/web commands, Tailscale Serve, configuration, and sheet automation.
   - Read [references/recipes.md](references/recipes.md) for reusable source patterns and debugging recipes.
   - Copy [assets/minimal-project.tjp](assets/minimal-project.tjp) when the user wants a new project skeleton.

## Workflow

1. Determine whether the user needs a new plan, a change to an existing plan, diagnosis, report design, or CLI operation.
2. Preserve an existing project's IDs, include boundaries, conventions, and output layout. Do not flatten `.tji` files without a reason.
3. Model outcomes and constraints before dates:

   - Build a hierarchical task tree.
   - Define resources and availability before allocating them.
   - Prefer dependencies and effort estimates over hard-coded task dates.
   - Use explicit IDs for every property that another property, report, or command will reference.

4. Choose exactly one leaf-task size model: `effort`, `length`, or `duration`. Leave a task without one to model a milestone. Let container tasks derive their span from children.
5. Add reports deliberately. A report without `formats` normally emits no file.
6. Validate in stages from the project directory:

   ```bash
   tj3 --silent --check-syntax plan.tjp
   tj3 --silent --no-reports plan.tjp
   tj3 --silent --no-reports --list-reports '.*' plan.tjp
   ```

   The first command only parses. The second also schedules and catches constraint/resource errors. The third exposes actual report IDs, including unwanted auto-generated IDs.

7. Generate all or selected reports into an existing output directory:

   ```bash
   tj3 --silent --output-dir build/reports plan.tjp
   tj3 --silent --output-dir build/reports --report overview plan.tjp
   tj3 --silent --output-dir build/reports --reports '^public\.' plan.tjp
   ```

8. Inspect the generated artifact or CSV structure, not only the process exit code. Report warnings separately from errors.
9. For private HTTPS publishing to a tailnet, use [scripts/serve-tailnet.sh](scripts/serve-tailnet.sh). Run it with `--build-only` when the user has not authorized changing the node's persistent Serve configuration. Never substitute Tailscale Funnel, which would make the report public.

## Core Guardrails

- Keep the mandatory `project` header in the main `.tjp`; use `.tji` for included fragments. Included paths are relative to the including file and use `/` separators.
- Define resources before tasks that allocate them. Define a property before supplementing or referencing it when the parser requires that ordering.
- Remember that task IDs are hierarchical, resource IDs are global, and report IDs are hierarchical. Never rely on auto-generated IDs.
- Place an inheritable attribute before child declarations when children should inherit it. List attributes append; use `purge <attribute>` before replacing an inherited list.
- Use `effort` when assigned work controls completion, `length` for working-time span, and `duration` for calendar-time span. Resource availability changes effort-task completion but does not extend `length` or `duration` tasks.
- Prefer ASAP chains with `start`/`depends`. `end`/`precedes` select ALAP; the last direction-setting attribute wins. Avoid mixing scheduling directions casually.
- Treat interval ends as exclusive. A date without a clock time is midnight, so an end date itself is not included.
- Set `timingresolution` before `timezone`, and define custom working hours after `timezone`. Project-header dates are UTC unless they include an explicit offset, even when `timezone` is set inside the header.
- Treat `complete` as reporting metadata; it does not reschedule work. Use bookings and a tracking scenario for actual resource usage.
- Treat `--freeze` and `--add-trace` as mutating operations. Review their target files and repository state first.
- Do not use `--force-reports` to conceal a broken schedule; generated results may be misleading.

## Delivery

Provide complete, idiomatic TJP snippets or focused edits. State which commands were run, whether parse and schedule validation both passed, which reports were generated, and any warnings that remain.
