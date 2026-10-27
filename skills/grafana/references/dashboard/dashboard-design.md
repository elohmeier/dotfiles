# Dashboard design reference

Use this for dashboard design, review, and restructuring. Start with `assets/dashboard/dashboard-design-brief.md`; panel choice and JSON structure follow from that contract.

## Contents

- [Source anchors](#source-anchors)
- [Write the design contract first](#write-the-design-contract-first)
- [Choose an operational strategy](#choose-an-operational-strategy)
- [Build an action path](#build-an-action-path)
- [Choose grouping and layout deliberately](#choose-grouping-and-layout-deliberately)
- [Design truthful visual comparisons](#design-truthful-visual-comparisons)
- [Define failure states](#define-failure-states)
- [Use color and interaction accessibly](#use-color-and-interaction-accessibly)
- [Variables, scope, and reuse](#variables-scope-and-reuse)
- [Set a performance budget](#set-a-performance-budget)
- [Documentation, ownership, and navigation](#documentation-ownership-and-navigation)
- [Validate with representative tasks and states](#validate-with-representative-tasks-and-states)
- [Management maturity](#management-maturity)
- [Design review checklist](#design-review-checklist)

## Source anchors

- Best practices: `docs/sources/visualizations/dashboards/build-dashboards/best-practices/index.md`
- Group dashboards with rows and tabs: `docs/sources/visualizations/dashboards/build-dashboards/create-dashboard/dashboard-groupings.md`
- Variables: `docs/sources/visualizations/dashboards/variables/_index.md`
- Add variables: `docs/sources/visualizations/dashboards/variables/add-template-variables/index.md`
- Variable syntax: `docs/sources/visualizations/dashboards/variables/variable-syntax/index.md`
- Dashboard links: `docs/sources/visualizations/dashboards/build-dashboards/manage-dashboard-links/`
- Panel options: `docs/sources/visualizations/panels-visualizations/configure-panel-options/index.md`
- Data links/actions: `docs/sources/visualizations/panels-visualizations/configure-data-links/index.md`

## Write the design contract first

Define these before choosing panels or writing queries:

- **Audience:** the primary role using the dashboard. Name a secondary role only if both perform the same workflow.
- **Job and decision:** what the user must determine or decide, not merely what data they can view.
- **Trigger:** alert, incident, routine review, capacity planning, release validation, or exploration.
- **Time contract:** default time range, refresh interval, expected ingestion delay, and the age at which data is stale.
- **State contract:** what normal, concerning, and critical mean, including the thresholds or comparisons that justify them.
- **Failure semantics:** how zero, no data, stale data, partial data, query errors, and permission errors differ.
- **Action path:** the next useful view, evidence, runbook, or owner for each concerning state.
- **Success criterion:** an observable task outcome, for example, “An on-call engineer identifies the affected service and reaches supporting logs within 30 seconds without losing scope or time context.”

Do not combine audiences that make different decisions or use different time horizons. An executive status view, an on-call troubleshooting view, a capacity-planning view, and an exploratory view usually deserve separate dashboards with links between them.

## Choose an operational strategy

Use RED for services:

- Rate: requests per second or throughput.
- Errors: error count or error ratio.
- Duration: latency distribution, usually percentiles or a histogram.

Use USE for infrastructure:

- Utilization: percent busy, for example CPU, memory, disk, or network.
- Saturation: queue length, load, throttling, or backlog.
- Errors: hardware, kernel, network, or device errors.

Use golden signals for user-facing systems:

- Latency, traffic, errors, and saturation.

These strategies organize evidence; they do not supply alert thresholds. Derive thresholds from an SLO, capacity limit, user-impact boundary, or historical baseline and document the rationale.

## Build an action path

Organize operational dashboards in the order users reason:

1. **Notice:** Is there user or system impact now? Show scope, freshness, and the few status signals that answer this.
2. **Interpret:** Which signals changed together? Align related trends to the same time range and make comparison scales honest.
3. **Inspect:** Which service, route, instance, dependency, or event explains the change?
4. **Act:** Link to the relevant logs, traces, profiles, alert, change event, owner, or runbook while preserving time and variable context.

The first screen should reveal current scope, data freshness, and status without opening a row or tab. Put contextual trends next and high-cardinality details lower in the flow.

## Choose grouping and layout deliberately

Use the smallest grouping model that matches the workflow:

| Choice                | Use when                                                                | Avoid when                                                                 |
| --------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Separate dashboard    | Audience, decision, time horizon, permissions, or ownership differs     | The same user only needs a sibling view of the same subject                |
| Tabs                  | Sibling views are mutually exclusive but share dashboard scope and time | Critical status would become hidden, or users need side-by-side comparison |
| Rows                  | The page has a top-to-bottom narrative or optional detail sections      | Rows merely compensate for an overfull dashboard                           |
| Fixed/custom grid     | Exact alignment and side-by-side comparison matter                      | Repeated content must adapt across widths                                  |
| Auto grid             | Repeated or similarly sized panels should respond to available width    | Specific 24-column placement carries meaning                               |
| Repeats               | One stable template must render for a bounded set of variable values    | The variable can create an unbounded number of panels or queries           |
| Conditional rendering | A view is irrelevant outside a known variable, data, or time condition  | Hiding it could conceal missing or critical evidence                       |

Rows, tabs, and nested layouts can each have section variables. A child panel resolves section variables before dashboard variables, so avoid reusing the same name at multiple scopes unless deliberate shadowing is required and documented.

Keep grouping shallow. Grafana's UI documentation supports up to three grouping levels; even when a schema permits deeper recursion, deeper nesting harms orientation and makes critical state easier to miss. Read `tabbed-dashboards-json.md` before authoring native tabs.

For panel layout:

- Align fixed layouts to the 24-column grid and make comparison panels the same size.
- Give dense legends and tables enough width. Avoid tiny time series.
- Prefer a few strong panels over many weak ones.
- Use rows for progressive disclosure, not as a default wrapper around every panel.
- Do not require horizontal scrolling to understand the main status at a narrow viewport.

## Design truthful visual comparisons

- Use a shared scale for side-by-side comparisons when the values are directly comparable. If scales differ, label that difference visibly.
- Start quantitative bar axes at zero. A truncated line-chart axis can be valid when the range is explicit and does not exaggerate change.
- Avoid dual axes unless the relationship is essential, both axes are labeled, and the visual cannot imply a false correlation.
- Normalize metrics when capacity differs, for example CPU percent instead of raw core-seconds.
- Split panels when one magnitude hides another.
- Stack only when the sum is meaningful and important individual behavior remains visible.
- Keep units, decimals, aggregation windows, and percentile labels explicit.
- Prefer direct labels or short stable legends. Do not expose unstable label sets or generated series names.

## Define failure states

Treat these as different states rather than rendering all of them as blank or zero:

| State             | Meaning                                                        | Design response                                                                    |
| ----------------- | -------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Zero              | The measured value is valid and equals zero                    | Show `0` with its unit and apply state semantics; do not replace it with “No data” |
| No data           | No matching frame, series, or sample exists                    | Use specific no-value text and explain likely causes or the next check             |
| Stale             | The last sample is older than the freshness contract           | Show sample age or a freshness signal and mark the dashboard as stale              |
| Partial           | Some expected targets, regions, shards, or sources are missing | Show expected versus reporting scope; do not summarize the subset as complete      |
| Query error       | Grafana or the data source could not execute the query         | Keep the error visible and provide a diagnostic path; never map it to healthy      |
| Permission denied | The user cannot access the data or destination                 | Distinguish access failure from empty data and provide an owner or access path     |

Set `fieldConfig.defaults.noValue` and value mappings intentionally. A friendly label is not enough for freshness or completeness: add a query or panel that compares the latest sample and expected reporting population with the contract. Do not connect gaps or coerce null to zero unless that interpretation is true for the metric.

## Use color and interaction accessibly

- Never make color the only state channel. Pair it with text, icons, thresholds, line styles, or direct labels.
- Use semantic colors consistently. Reserve red and orange for states that require attention; do not use the same color to encode an unrelated category.
- Verify text, grid lines, thresholds, and series in both light and dark themes.
- Prefer a color-blind-safe categorical palette and keep the number of simultaneous series low.
- Ensure titles, descriptions, and links state the question and destination. Avoid instructions that depend only on position or color, such as “click the green panel on the right.”
- Make important targets and table links usable at narrow widths and with keyboard navigation. Do not rely only on hover tooltips for essential meaning.

## Variables, scope, and reuse

- Use variables for datasource, cluster, namespace, service, instance, route, and environment instead of duplicating dashboards.
- Show current scope near the top and make “All” semantics explicit. An all-value regex must not silently broaden to a dangerous or expensive scope.
- For multi-value Prometheus label variables, use regex matchers (`=~`) in PromQL.
- Use `${var}` when embedding a variable in a word or when specifying format options.
- Use `${var:raw}`, `${var:csv}`, `${var:json}`, `${var:regex}`, or `${var:queryparam}` only when the target syntax requires it.
- Keep variable dependency chains short. Refresh datasource and scope variables only as often as their option set can change.
- Preserve current variables in dashboard links instead of copying dashboards.

## Set a performance budget

There is no universal safe panel or series limit. Set a target-specific budget before implementation and measure it with the real datasource, cardinality, and default time range.

Budget and review:

- Default time range and refresh interval relative to scrape interval, ingestion delay, and user need.
- Visible and preloaded panels, query count per refresh, repeated panels, and the maximum variable expansion.
- Series returned per query and total points after `maxDataPoints`, minimum interval, and downsampling.
- PromQL label cardinality, expensive joins or regexes, and long raw-range scans. Use recording rules for repeatedly expensive derived metrics.
- Variable query count, dependency depth, refresh behavior, and option count.
- Transformation cost and data transferred to the browser, especially joins and wide tables.

Use Query Inspector and datasource or dashboard insights to measure query time, response size, errors, and cache behavior. Test the cold load and refresh path. If a dashboard exceeds its budget, reduce default scope, aggregate earlier, split workflows, lazy-load secondary views, or move stable computation to recording rules.

## Documentation, ownership, and navigation

- State dashboard purpose, primary audience, owner, freshness, and runbook near the top. Keep text concise enough that it does not push status below the fold.
- Add panel descriptions when a query, transformation, threshold, unit, aggregation, or failure interpretation is not obvious.
- Use dashboard links for related workflows and data links for point-level drilldown.
- Preserve `from`, `to`, and relevant `var-*` values in drilldowns. Prefer links based on the clicked series, field, or labels.
- Add annotations for deployments, configuration changes, incidents, and alerts when they help explain time-correlated changes.
- Connect alert notifications to the relevant dashboard and scope. Connect the dashboard to logs, traces, and profiles rather than making users rebuild context.

## Validate with representative tasks and states

Validate behavior, not only JSON and panel rendering. Use a scenario such as:

> During an alert, an on-call engineer identifies whether users are affected, finds the affected service or route, and opens supporting evidence within 30 seconds without losing the selected scope or time range.

Test at least:

- Normal, concerning, and critical data near every threshold boundary.
- A valid zero and a gap with no data.
- Stale data, one missing region or target, a query error, and permission-denied drilldown.
- Single and multi-value variables, “All,” empty selections, special characters, and maximum expected repeat count.
- The default time range, a long time range, auto-refresh, known ingestion delay, and annotations.
- Wide and narrow viewports, long labels, keyboard navigation, and both light and dark themes.
- Dashboard and data links, including preserved time and variable context.
- Cold-load and refresh performance with production-like cardinality.

Inspect the final data frames in panel Inspect/Data and use transformation debug. Schema-valid JSON can still be operationally misleading.

## Management maturity

Low maturity signs:

- Many copied dashboards, no clear owner, little reuse, no version control, and random browsing to find dashboards.

Medium maturity:

- Template variables prevent per-node or per-service clones.
- Dashboards reflect a strategy such as RED or USE.
- Drilldowns guide users from overview to detail.
- JSON is version controlled.

High maturity:

- Dashboards have explicit design contracts, owners, task tests, and performance budgets.
- Sprawl is actively reduced.
- Dashboards are generated or templated for consistency.
- Production dashboard edits are controlled.
- Usage is reviewed and obsolete dashboards are removed.

## Design review checklist

- Who uses this, what triggers use, and what decision must they make?
- Can the first screen reveal user impact, current scope, and data freshness?
- Are normal, concerning, critical, zero, no-data, stale, partial, error, and permission states distinguishable?
- Does grouping match the workflow, and is critical evidence visible without opening a tab or collapsed row?
- Are comparisons, scales, units, aggregations, thresholds, labels, and legends honest and documented?
- Can users move from symptom to evidence and action without losing scope or time?
- Are variables reducing copies without producing unbounded queries or panels?
- Is the dashboard within its measured performance budget?
- Does it work at narrow widths, in light and dark themes, without color as the only state channel?
- Can a representative user complete the named task within the success criterion?
