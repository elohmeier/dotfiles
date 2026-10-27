# TaskJuggler Language and Scheduling Model

## Contents

- [Compiler model](#compiler-model)
- [Files and declaration order](#files-and-declaration-order)
- [Lexical syntax](#lexical-syntax)
- [Properties, IDs, and inheritance](#properties-ids-and-inheritance)
- [Tasks and scheduling](#tasks-and-scheduling)
- [Resources and calendars](#resources-and-calendars)
- [Time semantics](#time-semantics)
- [Scenarios](#scenarios)
- [Reports](#reports)
- [Progress and actuals](#progress-and-actuals)
- [Common mistakes](#common-mistakes)

## Compiler Model

TaskJuggler reads source, expands includes/macros, parses properties, schedules every active scenario, checks the result, and generates declared reports. The source should state what must be true; computed dates and allocations are outputs.

The scheduler is heuristic resource leveling, not a global optimizer. It schedules ready leaf tasks by explicit priority, path/resource criticalness, and declaration order. Use `priority` only to influence competition for resources, not as a substitute for dependencies.

## Files and Declaration Order

- Put the mandatory `project` header in one main `.tjp` file. Only a macro-only include may precede it.
- Put reusable or separated fragments in `.tji` files.
- Use `include "path/file.tji"`. Relative includes and report output names inside an include resolve relative to that included file.
- Use `include.project` inside the project header, `include.properties` among property declarations, and `include.macro` before the project header. Query these qualified names with `tj3man` when placement matters.
- Pass additional `.tji` fragments positionally to `tj3` when they are intentionally outside the include graph, for example a shared report file.
- Define referenced objects before use. A practical order is macros, flags, accounts, shifts/leaves, resources, tasks, reports, and exports.
- Use `supplement task <absolute-id>`, `supplement resource <id>`, `supplement account <id>`, or `supplement report <absolute-id>` to add attributes to an already defined property from another file.

## Lexical Syntax

Properties generally have a keyword, optional ID, required quoted name, and optional attributes:

```tjp
task build "Build release" {
  effort 8d
  allocate developer
}
```

- IDs begin with a letter or underscore and then contain letters, digits, or underscores.
- Quote names and strings with single or double quotes.
- Use `-8<-` and `->8-` for indentation-aware multiline strings. Keep the closing indentation consistent.
- Use `#`, `//`, or `/* ... */` comments.
- Define text macros as `macro Name [ ... ]` and call them as `${Name}` or `${Name "argument"}`. Prefer an uppercase initial for user macros; lowercase names are reserved for built-ins. The terminating `]` of a multiline macro must be the final character on its line.
- Use built-ins such as `${projectstart}`, `${projectend}`, `${now}`, and `${today}` only after the project header makes them available.
- Use `%{${projectstart} + 2w}` for date arithmetic. Preserve spaces around the operator.
- `$(NAME)` expands an environment variable whose name contains uppercase ASCII letters, digits, or underscores. Do not expose secrets through generated reports.

Run `tj3man` without a keyword to list all grammar entries. The installed syntax reference is generated from the parser and is the authority for keyword contexts and attributes.

## Properties, IDs, and Inheritance

TaskJuggler properties include projects, accounts, shifts, resources, tasks, navigators, and reports.

- Tasks have hierarchical IDs. Inside task `release`, child `test` has absolute ID `release.test`. Sibling references can use `!test`; each leading `!` moves lookup to one enclosing task scope.
- Resources have a global ID namespace even when nested into groups.
- Accounts and reports have hierarchical namespaces.
- Different property classes may reuse an ID, but avoid confusing reuse in compact files.
- Auto-generated IDs can change. Give a stable ID to anything referenced by a dependency, supplement, report composition, CLI `--report`, or filter.

Many attributes inherit from global or parent scope. Placement is significant:

```tjp
task phase "Phase" {
  priority 700       # inherited by children declared below
  flags internal     # list starts with internal

  task work "Work" {
    flags billable   # appends: internal, billable
  }

  task public "Public work" {
    purge flags
    flags billable   # replaces the inherited list
  }
}
```

Check the `[ig]`, `[ip]`, and `[sc]` markers in `tj3man <keyword>` for global inheritance, parent inheritance, and scenario specificity.

## Tasks and Scheduling

Use a task tree as the work breakdown structure:

- A container task has subtasks and derives its start/end from them. Do not give it `effort`, `length`, or `duration`.
- A milestone has no subtasks and no size attribute. Give it a start/end criterion or dependency.
- A regular leaf task has exactly one size model:

| Attribute  | Meaning                                    | Resource effect                                                                          |
| ---------- | ------------------------------------------ | ---------------------------------------------------------------------------------------- |
| `effort`   | Resource work, such as `10d` resource-days | Availability determines when the required work completes; allocate at least one resource |
| `length`   | Working-time span                          | Global/shift working time determines the span; missing allocations do not extend it      |
| `duration` | Calendar-time span                         | Elapsed time determines the span; `7d` is one calendar week                              |

Adding people to `effort` can shorten a task only when its work is genuinely parallelizable. Model coordination or sequential work as subtasks instead of assuming perfect division.

### Constraints and direction

- `start <date>` or `depends <task>` selects ASAP scheduling.
- `end <date>` or `precedes <task>` selects ALAP scheduling.
- `depends` means this task cannot start until the referenced task finishes.
- `precedes` means the referenced task cannot start until this task finishes.
- Add working-time gaps with `gaplength`; add elapsed-time gaps with `gapduration` on a dependency.
- If multiple direction-setting attributes occur, the last one determines direction. Put `scheduling asap|alap` last only when an explicit override is necessary.
- Prefer consistent ASAP dependency chains. Mixed ASAP/ALAP chains are slower and can produce priority inversion.
- `start` is a not-before constraint and may move later for resource availability. `end` is a not-after constraint and may move earlier.
- `minstart`, `maxstart`, `minend`, and `maxend` are post-schedule checks, not all scheduling inputs. Confirm each exact keyword with `tj3man`.
- Use `priority 1..1000` to influence resource contention. The default is 500; higher does not directly mean earlier.

## Resources and Calendars

Define individual resources or nested groups before allocating them:

```tjp
resource engineering "Engineering" {
  resource alice "Alice"
  resource bob "Bob" {
    leaves annual 2026-07-20 - 2026-08-03
    limits { weeklymax 32h }
  }
}
```

For direct assignment, use `allocate alice, bob`. For one interchangeable resource, use alternatives:

```tjp
allocate alice {
  alternative bob
  select minallocated
  persistent
}
```

- `alternative` creates a candidate set; it does not allocate all candidates.
- `persistent` keeps the chosen alternative across breaks.
- `mandatory` makes an allocation group all-or-nothing for each time slot.
- Resource leaves, shifts, working hours, efficiency, and limits affect availability.
- `length` uses global working hours or task shifts to measure task span; a resource's own calendar determines allocations but does not redefine that span.
- Global and nested list attributes accumulate unless purged.

## Time Semantics

- Dates resemble ISO 8601: `YYYY-MM-DD[-hh:mm[:ss]][-+HHMM]`.
- Project time is stored in UTC. The `timezone` setting interprets later dates without offsets, but does not reinterpret start/end dates already written in the project header. Add an explicit offset there when needed.
- Intervals are half-open. `2026-03-01 - 2026-03-05` ends at midnight at the start of March 5, so March 5 is excluded.
- Use `start +4m` or `start - end` for the project interval.
- `timingresolution` defaults to one hour and supports 5, 10, 15, 30, or 60 minutes. Smaller slots cost memory and scheduling time; all specified times must align.
- If changing defaults, set `timingresolution` first, `timezone` next, and `workinghours` afterward because time-zone/resolution changes can reset working hours.
- `dailyworkinghours` controls conversion between working hours and working days; its default is 8.

## Scenarios

The default project has one `plan` scenario. Define a hierarchy inside the project header for baselines, actuals, or what-if schedules:

```tjp
project product "Product" 2026-01-01 +6m {
  scenario plan "Plan" {
    scenario actual "Actual"
    scenario optimistic "Optimistic"
  }
}

task delivery "Delivery" {
  effort 20d
  actual:effort 24d
  optimistic:effort 16d
  allocate alice
}
```

- All scenarios share the same property tree; only scenario-specific attributes vary.
- A child inherits the parent's value unless overridden.
- Declaration order matters: setting a parent scenario value after a child-specific value can overwrite the child because the value propagates downward.
- Select scenarios in reports with `scenarios` (plural for table reports) or the report-type-specific singular `scenario` where documented.
- Mark one scenario with `trackingscenario` before using bookings or time/status sheets.

## Reports

Reports are source declarations evaluated after scheduling. Common types are:

- `taskreport`: task table and optional Gantt chart.
- `resourcereport`: resources, load, and assigned tasks.
- `textreport`: Rich Text composition of other report blocks.
- `accountreport`: account/balance view.
- `icalreport`: RFC 5545 calendar output.
- `export`: scheduled TJP/TJI or Microsoft Project XML.
- `tracereport`: values appended over repeated `--add-trace` runs.
- `timesheetreport` and `statussheetreport`: `.tji` sheet templates.

For task/resource/text reports, output formats include `html`, `csv`, and `niku`. An empty `formats` list means no standalone file, which is useful for nested report components.

```tjp
taskreport overview "overview" {
  formats html, csv
  columns bsi, name, start, end, effort, resources, chart
  hideresource @all
  sorttasks tree, plan.start.up
}
```

- The report name becomes the output basename; the ID is what `--report` addresses.
- Reports can nest and inherit report attributes. Use explicit IDs for composed or CLI-selected reports.
- `hidetask`, `hideresource`, and `hideaccount` hide properties for which their logical expression is true. For example, after declaring flag `public`, `hidetask ~public` keeps public tasks by hiding tasks without the flag.
- Default tree sorting may retain hidden parents to preserve hierarchy.
- Restrict expensive or large reports with `period`, roots, filters, sorting, and explicit columns.

## Progress and Actuals

- `now` changes TaskJuggler's current date for calculations and reports.
- `complete 0..100` affects completion/gauge reporting only; it does not alter scheduling, assignments, total effort, or remaining effort.
- `booking` records exact historical resource usage. Prefer generated bookings over hand-authored slot data.
- `trackingscenario` identifies the actual scenario and enables projection behavior for it and derived scenarios.
- `tj3 --freeze --freezedate <date> plan.tjp` generates/updates `<base>-header.tji` and `<base>-bookings.tji` in the working directory. Include the header fragment at the end of the project header and bookings at the end of the project source. Review generated changes before committing.

## Common Mistakes

- Passing syntax validation but never running a schedule-only validation.
- Giving an effort task no resource or assuming effort always divides linearly across people.
- Giving size attributes to containers or accidentally turning a zero-size leaf into a milestone.
- Confusing working `length` with calendar `duration`.
- Relying on a resource calendar to extend a length/duration task.
- Omitting IDs and then receiving unstable report IDs such as `report3`.
- Reversing `hidetask` logic: it removes matches.
- Defining an inheritable attribute after the child that was meant to inherit it.
- Forgetting that list values append and require `purge` to replace.
- Treating project-header dates as local time because `timezone` appears later in the header.
- Using an end date as inclusive.
- Generating all reports while debugging one report, creating unrelated output churn.
