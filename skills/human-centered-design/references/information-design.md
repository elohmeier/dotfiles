# Information Design

Use this reference for dashboards, reports, charts, maps, tables, instructions, operational displays, and other dense information surfaces.

## Purpose Before Chart Type

Start with the decision or question:

- Compare values?
- See distribution?
- Track change over time?
- Detect exception?
- Understand relationship?
- Locate in space?
- Follow a sequence?
- Explain causality or evidence?

Choose the representation after the task is clear.

## Escape Flatness

Complex information often has many dimensions: time, space, hierarchy, category, quantity, uncertainty, and annotation. A good display increases useful dimensionality without making interpretation fragile.

Use:

- Position and alignment for comparison.
- Layering for context and focus.
- Small multiples for repeated comparison.
- Annotation for interpretation.
- Interaction for filtering, details, and alternate views.

## Micro And Macro Readings

Good displays support both overview and close reading.

- Macro: pattern, trend, outlier, scope, status.
- Micro: exact value, label, event, exception, evidence.

Do not make users choose between a pretty overview and the details needed to act.

## Layering And Separation

Separate information by visual weight, spacing, position, enclosure, and muted support elements. Gridlines, borders, backgrounds, and labels should help the data read clearly.

Prefer:

- Light scaffolding.
- Strong data marks.
- Consistent alignment.
- Direct labels when legends slow comparison.
- Grouping by analytical meaning.

Avoid decorative containers that compete with the information.

## Small Multiples

Use small multiples when users must compare the same measure across categories, places, time windows, cohorts, or scenarios.

Keep:

- Same scales where comparison requires it.
- Same layout and encoding.
- Clear labels.
- Enough repetition for pattern recognition.

Use independent scales only when local shape matters more than magnitude comparison, and label that choice.

## Color And Information

Color is powerful and easy to misuse.

Use color for:

- Category distinction when categories are few.
- Sequential magnitude.
- Diverging values around a meaningful center.
- Alert status.
- Selection and focus.

Check color vision deficiencies, contrast, print/export, dark mode, and whether color semantics conflict with domain conventions.

## Time, Space, And Narrative

When information unfolds over time or place, show sequence and context.

Patterns:

- Timeline with events and state changes.
- Map with scale and meaningful layers.
- Sankey or flow only when flow magnitude matters and labels remain readable.
- Step diagram for procedures.
- Before/after or version comparison for change.

Narrative should guide attention without hiding evidence.

## Tables

Tables are often the right answer for exact lookup, comparison across many attributes, and operational action.

Design tables with:

- Clear default sort.
- Sticky headers when useful.
- Aligned numbers.
- Units in headers.
- Meaningful empty values.
- Filtering and search.
- Row actions that do not crowd scanning.
- Copy/export where users need downstream work.

## Dashboard Review

Ask:

- What decision will this display change?
- What is the time range and data freshness?
- What is missing or delayed?
- What is normal, concerning, and critical?
- What action should follow each state?
- Can users compare without decoding legends repeatedly?
- Does the display explain uncertainty and data quality?
