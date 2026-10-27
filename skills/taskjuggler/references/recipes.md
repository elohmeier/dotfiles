# TaskJuggler Recipes

Use these as patterns, then confirm every less-common attribute with `tj3man` and validate the complete project.

## Start a Project

Copy `assets/minimal-project.tjp`, then change the project ID/name/interval, timezone, resources, task tree, estimates, and report names. Validate before generating reports:

```bash
tj3 --check-syntax project.tjp
tj3 --no-reports project.tjp
tj3 --no-reports --list-reports '.*' project.tjp
```

## Dependency Chains and Gaps

Prefer dependencies over copied dates:

```tjp
task delivery "Delivery" {
  task design "Design" {
    start ${projectstart}
    effort 5d
    allocate alice
  }

  task build "Build" {
    depends !design
    effort 10d
    allocate alice
  }

  task launch "Launch" {
    depends !build { gaplength 2d }
  }
}
```

`gaplength 2d` adds two working days. Use `gapduration 2d` for two elapsed calendar days. The last task has no size and is therefore a milestone.

## Choose the Correct Size Model

```tjp
# Finishes after 12 resource-days have actually been assigned.
task implementation "Implementation" {
  effort 12d
  allocate alice, bob
}

# Spans five working days even if no resource is available for some slots.
task review_window "Review window" {
  length 5d
  allocate reviewer
}

# Spans seven calendar days, including non-working days.
task cooling_off "Cooling-off period" {
  duration 7d
}
```

Split non-parallel work into subtasks instead of adding resources to one effort estimate.

## Pick One Resource from Alternatives

```tjp
task ux_review "UX review" {
  effort 2d
  allocate alice {
    alternative bob, carol
    select minallocated
    persistent
  }
}
```

This requests one of the three people, keeps the chosen person across breaks, and favors the candidate with the lowest allocation factor. Remove `persistent` when switching after an availability break is acceptable.

For simultaneous participants, use separate mandatory allocations and confirm exact behavior for the installed version:

```tjp
allocate facilitator { mandatory }
allocate reviewer { mandatory }
```

## Split a Project into Includes

```text
project.tjp
includes/
  resources.tji
  tasks.tji
  reports.tji
```

```tjp
project example "Example" 2026-01-01 +6m {
  timezone "Europe/Berlin"
}

include "includes/resources.tji"
include "includes/tasks.tji"
include "includes/reports.tji"
```

The include acts as inline source at that location, so order remains significant. Paths nested inside `reports.tji` resolve relative to `reports.tji`, not necessarily the shell's working directory.

Use a supplement when ownership is split but the base property already exists:

```tjp
supplement task delivery.build {
  note "Runbook: https://example.invalid/build"
  flags public
}
```

## Compare Scenarios

```tjp
project product "Product" 2026-01-01 +6m {
  scenario plan "Plan" {
    scenario actual "Actual"
    scenario risk "Risk case"
  }
}

resource alice "Alice"

task build "Build" {
  start ${projectstart}
  effort 10d
  actual:effort 12d
  risk:effort 16d
  allocate alice
}

taskreport comparison "comparison" {
  formats html
  scenarios plan, actual, risk
  columns name, start, end, effort, chart
}
```

Set the base value before child overrides so downward scenario inheritance does not replace the overrides.

## Create Focused Reports

Declare flags before using them:

```tjp
flags public, internal

taskreport public_schedule "public-schedule" {
  formats html, csv
  columns bsi, name, start, end, resources, chart
  hidetask ~public
  hideresource @all
  sorttasks tree, plan.start.up
}

resourcereport capacity "capacity" {
  formats html
  columns name, effort, freework, fte, weekly
  hideresource ~isleaf()
  hidetask @none
}
```

`hide...` removes matches. `hidetask ~public` therefore removes tasks without `public`. Test filtering on representative parents and leaves because default tree sorting may keep enclosing properties.

## Diagnose a Broken Project

1. Run `tj3 --check-syntax` and fix the first parser error before interpreting later ones.
2. Query the reported keyword and context with `tj3man`.
3. Run `tj3 --no-reports` to expose schedule errors.
4. For an unschedulable leaf, check:

   - one and only one of `effort`, `length`, or `duration`;
   - an ASAP start criterion (`start`/`depends`) or ALAP end criterion (`end`/`precedes`);
   - an allocated resource for `effort`;
   - resource availability, leaves, limits, and timing alignment;
   - dependency cycles or references in the wrong task scope;
   - project interval large enough to contain the result.

5. For wrong allocations, inspect priorities, alternatives, mandatory/persistent selection, resource calendars, and whether a length/duration task was expected to wait for resources.
6. For a missing report file, run `--list-reports '.*'`, confirm a stable ID, nonempty `formats`, output basename, filters, and output directory.
7. Generate one report by exact ID and inspect it before restoring the full report set.

## Track Actual Work Carefully

Use `complete` only for visual progress metadata:

```tjp
supplement task delivery.build {
  complete 60
}
```

For auditable resource history, define a tracking scenario and use bookings/time sheets. Before freezing:

1. Commit or otherwise preserve current project sources.
2. Set and verify `trackingscenario`.
3. Run syntax and schedule validation.
4. Choose an explicit freeze cutoff aligned with the project resolution.
5. Run `tj3 --freeze --freezedate YYYY-MM-DD project.tjp` from the intended project directory.
6. Include the generated header and bookings fragments at their required positions.
7. Rerun validation and review all generated diffs.
