# Dashboard design brief

Complete this before writing dashboard JSON. Delete instructional text and examples from the finished brief.

## Identity and task

- **Dashboard title:**
- **Owner and contact:**
- **Primary audience:**
- **Trigger:** Alert, incident, routine review, release validation, capacity planning, or exploration.
- **Job or decision:** “When ___, the user must determine/decide ___.”
- **Success criterion:** “A representative user can ___ within ___ without ___.”
- **Out of scope:**

If another audience makes a different decision or uses a different time horizon, create a linked dashboard for that workflow.

## Data and time contract

| Contract item                 | Decision                                           |
| ----------------------------- | -------------------------------------------------- |
| Data sources and owners       |                                                    |
| Default time range            |                                                    |
| Refresh interval              |                                                    |
| Scrape or event interval      |                                                    |
| Expected ingestion delay      |                                                    |
| Stale after                   |                                                    |
| Expected reporting population | For example, regions, shards, targets, or services |
| Known gaps or caveats         |                                                    |

## State and action contract

| State             | Observable definition | User-facing treatment                | Next action or destination                    |
| ----------------- | --------------------- | ------------------------------------ | --------------------------------------------- |
| Normal            |                       |                                      |                                               |
| Concerning        |                       |                                      |                                               |
| Critical          |                       |                                      |                                               |
| Valid zero        |                       | Show `0` with the correct unit       |                                               |
| No data           |                       | Never imply healthy                  |                                               |
| Stale             |                       | Show sample age or freshness failure |                                               |
| Partial data      |                       | Show expected versus reporting scope |                                               |
| Query error       |                       | Keep the error visible               | Query Inspector, datasource owner, or runbook |
| Permission denied |                       | Distinguish from empty data          | Access request or owner                       |

Thresholds must come from an SLO, capacity limit, user-impact boundary, or documented baseline. Record the source here:

## Information architecture

Write the shortest path from notice to action:

1. **Notice:**
2. **Interpret:**
3. **Inspect:**
4. **Act:**

Choose grouping deliberately:

- **Separate dashboards:** audiences, decisions, time horizons, permissions, or ownership that differ.
- **Tabs:** mutually exclusive sibling views that share scope; never hide critical status.
- **Rows:** top-to-bottom narrative or optional detail.
- **Fixed grid:** precise alignment and comparison.
- **Auto grid:** responsive, repeated, similarly sized panels.
- **Conditional rendering:** relevance only; never conceal missing or critical evidence.

Record the chosen structure and why:

## Panel inventory

| Order | Panel question | Query/data shape | Visualization | Unit and aggregation | Threshold source | Zero/no-data/stale treatment | Drilldown/action |
| ----- | -------------- | ---------------- | ------------- | -------------------- | ---------------- | ---------------------------- | ---------------- |
| 1     |                |                  |               |                      |                  |                              |                  |

Remove any panel that does not support the job, decision, or action path.

## Variables and interactions

| Variable | Scope and allowed values | Default and “All” semantics | Refresh | Maximum expansion |
| -------- | ------------------------ | --------------------------- | ------- | ----------------- |
|          |                          |                             |         |                   |

- **Dashboard links:**
- **Data links to logs/traces/profiles:**
- **Runbook and owner links:**
- **Context to preserve:** `from`, `to`, and relevant `var-*` values.
- **Annotations:** Deployments, configuration changes, incidents, or alerts.

## Performance budget

Set target-specific limits and verify them against production-like data.

| Budget item                       | Target | Measured result |
| --------------------------------- | ------ | --------------- |
| Cold load to useful status        |        |                 |
| Refresh completion                |        |                 |
| Visible/preloaded panels          |        |                 |
| Queries per refresh               |        |                 |
| Series per query and total points |        |                 |
| Variable query depth/options      |        |                 |
| Maximum repeated panels/queries   |        |                 |
| Browser transformation/data size  |        |                 |

Record required recording rules, downsampling, `maxDataPoints`, minimum intervals, lazy loading, or scope limits:

## Accessibility and visual integrity

- [ ] Color is not the only state channel.
- [ ] Semantic colors are consistent and categorical colors are distinguishable.
- [ ] Text, grid lines, series, thresholds, and links work in light and dark themes.
- [ ] Comparisons use honest scales; bars start at zero; dual axes do not imply false correlation.
- [ ] Units, aggregation windows, percentiles, labels, and legends are explicit.
- [ ] Essential meaning is available without hover and important links work by keyboard.
- [ ] Main status and actions remain usable at a narrow viewport without horizontal scrolling.

## Validation scenarios

Record evidence and issues for each scenario:

| Scenario                                                 | Expected result | Evidence or issue |
| -------------------------------------------------------- | --------------- | ----------------- |
| Normal, concerning, and critical thresholds              |                 |                   |
| Valid zero versus no data                                |                 |                   |
| Stale and partial data                                   |                 |                   |
| Query error and permission-denied drilldown              |                 |                   |
| Single, multi, “All,” empty, and maximum variable scopes |                 |                   |
| Default, long, and delayed time ranges                   |                 |                   |
| Wide/narrow and light/dark                               |                 |                   |
| Cold load and refresh at production cardinality          |                 |                   |
| Notice-to-action representative task                     |                 |                   |

## Review

- **Design owner:**
- **Datasource owner:**
- **Primary-user reviewer:**
- **Last validated:**
- **Revalidate after:** Metric/label changes, SLO changes, datasource migrations, major Grafana upgrades, or workflow changes.
