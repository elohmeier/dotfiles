# Fletcher Diagrams and Lucide Icons

Use this reference for presentation flowcharts, architecture diagrams, process loops, and supporting iconography. Read `user-layout.md` too when the diagram sits inside a slide, grid, card, or fixed-height region.

## Contents

- Package and font setup
- Reusable presentation pattern
- Fletcher layout guidance
- Lucide icon guidance
- Presentation and validation checklist

## Package And Font Setup

Preserve an existing project's package pins. For a new document, verify package and compiler compatibility, render a representative diagram, and then pin the versions. The following imports match a proven presentation setup:

```typst
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/lucide:0.1.0": lucide-icon
```

Keep the `fletcher` module alias when using submodules such as `fletcher.shapes.rect` or helpers such as `fletcher.hide`. Import Lucide's callable explicitly instead of using `*`.

Lucide 0.1.0 renders through the external `lucide` icon font; the package does not bundle the font. Check availability before debugging missing glyphs:

```sh
typst fonts | rg -i '^lucide$'
```

If absent, install the matching Lucide TTF or keep it in a project font directory and pass `--font-path <dir>`. With `@preview/lucide:0.1.0`, call `lucide-icon`; `lucide-inline` is not exported by the package even though stale examples may show it.

## Reusable Presentation Pattern

Centralize icon, card, diagram, and frame styling. Let Fletcher draw the node outline and connectors; let the card helper arrange the icon and text inside the node.

```typst
#import "@preview/fletcher:0.5.8" as fletcher: diagram, node, edge
#import "@preview/lucide:0.1.0": lucide-icon

#let accent = rgb("#009fe3")
#let ink = rgb("#003b64")
#let muted = rgb("#315f79")
#let pale = rgb("#f4fbfe")
#let border = rgb("#b9e4f5")

#set page(width: 13.333in, height: 7.5in, margin: 0.7in, fill: luma(94%))
#set text(size: 14pt, fill: ink)

#let flow-icon(name, size: 15pt) = lucide-icon(name, size: size, fill: accent)

#let flow-card(icon-name, title, sub, width: 1.55in) = box(width: width)[
  #set align(center)
  #set par(spacing: 0pt, leading: 0.3em)
  #flow-icon(icon-name)
  #v(0.03in)
  #text(weight: "bold", title)
  #v(0.02in)
  #text(size: 10pt, fill: muted, sub)
]

#let flow-diagram(..args) = diagram(
  node-shape: fletcher.shapes.rect,
  node-stroke: 0.7pt + border,
  node-fill: white,
  node-corner-radius: 0.09in,
  node-inset: 9pt,
  edge-stroke: 1.5pt + accent,
  mark-scale: 130%,
  spacing: (0.44in, 0.46in),
  ..args,
)

#let diagram-frame(body) = block(
  width: 100%,
  inset: 10pt,
  radius: 0.12in,
  fill: white,
  stroke: 0.7pt + border,
)[
  #block(width: 100%, inset: 0.18in, radius: 0.1in, fill: pale)[
    #align(center)[#body]
  ]
]

#align(center + horizon)[
  #diagram-frame[
    #flow-diagram(
      node((0, 0), flow-card("message-circle", [Question], [Goal + context]), name: <question>),
      edge("-|>"),
      node((1, 0), flow-card("activity", [Model], [Plans next step]), name: <model>),
      edge("-|>"),
      node((2, 0), flow-card("wrench", [Tool call], [Name + arguments]), name: <tool>),
      node((2, 1), flow-card("list-checks", [Result], [Compact evidence]), name: <result>),
      node((1, 1), flow-card("message-circle", [Answer], [Finding + limits]), name: <answer>),
      edge(<tool>, (3, 0), (3, 1), <result>, "-|>"),
      edge(<result>, <answer>, "-|>"),
      edge(<answer>, <model>, "-|>"),
    )
  ]
]
```

## Fletcher Layout Guidance

- Draft on Fletcher's default elastic grid: `(column, row)`, with `(0, 0)` at the upper left under the default `axes: (ltr, ttb)`.
- Interleave `edge("-|>")` between two nodes only for a simple source-order connection. Give meaningful names such as `<tool>` and use explicit endpoints for branches, loops, and later edits.
- Route orthogonal returns with intermediate coordinates, for example `edge(<tool>, (3, 0), (3, 1), <result>, "-|>")`. These waypoints participate in the diagram bounds, so recheck centering and frame width.
- Use `"-|>"` for the solid presentation arrowhead. Tune `edge-stroke` and `mark-scale` together so the line and tip have balanced visual weight.
- Treat `spacing` as the gap between elastic grid cells, not a fixed center-to-center distance. Node content determines each row and column size.
- Give the inner card a stable width when nodes should look uniform. Fletcher's `node-inset` adds padding outside that label, so avoid duplicating large insets in both layers.
- Put shared shape, fill, stroke, radius, inset, spacing, and arrow defaults in one diagram wrapper. Apply exceptional `fill` or `stroke` on an individual `node` to show a boundary or decision point.
- Temporarily set `debug: 1` on `diagram` while tuning positions. For staged presentation builds, use `fletcher.hide(objects, bounds: true)` so hidden nodes still reserve their final layout.

## Lucide Icon Guidance

- Wrap `lucide-icon` once to centralize size and color. It forwards styling arguments to `text`, so `size` and `fill` are the normal controls.
- Use kebab-case icon names such as `message-circle`, `activity`, `wrench`, `shield-check`, `server`, `database`, and `list-checks`.
- Verify every icon visually. An unknown name is not guaranteed to produce a useful compile error because the package falls back to rendering the supplied name through the icon font.
- Keep icons supportive and redundant with the node title. Do not encode a state or step only through an icon or color.
- Use a small, consistent size inside flow cards and a larger size only for intentional single-message slides. Place icons on their own centered line when font baselines make inline alignment look uneven.

## Presentation And Validation Checklist

- Keep node titles short; move qualifications into a smaller second line.
- Prefer one dominant flow direction and route feedback edges around, not through, cards.
- Compile from the intended project root when slides reference shared templates or assets: `typst compile --root . path/to/slides.typ out.pdf`.
- Render the affected slide at 144 PPI and inspect it. Check connector snapping, arrow direction, waypoint clearance, uniform card widths, wrapped titles, missing/tofu icons, and frame centering.
- Re-render every slide that uses a changed helper; a wrapper edit affects all call sites.
