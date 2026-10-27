# Typst User Layout

Use this reference for layout, sizing, alignment, boxes, blocks, pages, grids, and measurements in user-facing Typst documents.

## Inline, Paragraph, And Block Content

Typst automatically groups inline content into paragraphs.

Inline-level content includes text, `h`, `box`, and inline math. Block-level content includes `block`, `place`, figures, tables, headings, and most layout containers.

Use `box` when something must participate in a line:

```typst
Status: #box(
  inset: (x: 4pt, y: 1pt),
  radius: 2pt,
  fill: green.lighten(70%),
)[Done]
```

Use `block` when content should stand on its own and interrupt the paragraph:

```typst
#block(
  width: 70%,
  inset: 10pt,
  fill: luma(245),
  radius: 4pt,
)[
  This is a separate block.
]
```

Paragraph styling such as `first-line-indent` applies only to real paragraphs. Wrapping text in `block[...]` can intentionally prevent paragraph semantics; adding `parbreak()` can force paragraph creation inside generated content.

## Alignment

`align` is block-level and interrupts the current paragraph:

```typst
#align(center)[Centered block]
#align(right + bottom, block(height: 4cm)[Bottom right])
```

For same-line alignment, use flexible horizontal spacing:

```typst
Left #h(1fr) Right
```

Use logical alignment for language-aware documents:

- `start` and `end` follow `text.dir`.
- `left` and `right` are physical.
- `top`, `horizon`, and `bottom` are vertical.
- Combine axes with `+`, such as `right + horizon`.

Nested alignment works because containers and their content can have different alignments:

```typst
#align(center, block(width: 70%)[
  #set align(left)
  The block is centered, but this text is left-aligned inside it.
])
```

## Sizing

Common size values:

- Absolute: `12pt`, `3cm`, `1in`
- Font-relative: `1em`
- Parent-relative: `50%`
- Fractional: `1fr`, `2fr`
- Automatic: `auto`

`auto` generally fits content. Percentages resolve against the available container size. Fractions divide remaining free space in contexts that support them, such as `grid` tracks, `h(1fr)`, stack spacing, and some box/block sizing situations.

Examples:

```typst
#rect(width: 50%, height: 2cm)

Left #h(1fr) Center #h(1fr) Right

#grid(
  columns: (1fr, 2fr, auto),
  [A], [Wider], [Fit],
)
```

Avoid fixed heights for flowing text unless overflow or page-breaking behavior is intentional.

## Insets, Outsets, Stroke, And Clip

`inset` pads the content and affects layout size. `outset` grows paint or clipping bounds without changing layout size.

```typst
#box(
  inset: (x: 4pt, y: 1pt),
  outset: (y: 2pt),
  fill: luma(235),
  radius: 2pt,
)[Inline label]
```

Use `clip: true` when oversized content should be hidden:

```typst
#box(width: 4cm, height: 2cm, clip: true)[
  #image("wide.png", width: 8cm)
]
```

Relative insets are relative to the box/block size, while relative widths and heights are relative to the containing size. This matters when mixing percentages with padding.

## Pages And Columns

Page setup:

```typst
#set page(
  paper: "a4",
  margin: (x: 2.5cm, y: 2cm),
  numbering: "1",
)
```

Columns:

```typst
#columns(2, gutter: 1cm)[
  #lorem(120)
]
```

Use `colbreak()` inside columns. Use `pagebreak()` at the document/page level.

## Grids And Tables

Use `grid` for layout. Use `table` for semantic tabular content.

```typst
#grid(
  columns: (auto, 1fr),
  gutter: 8pt,
  [Label], [Value that can wrap],
)
```

Cell alignment can be global, column-wise, or per cell:

```typst
#table(
  columns: (1fr, auto),
  align: (left, right),
  table.header([Item], [Price]),
  [Tea], [$2.50],
  [Coffee], [$3.00],
)
```

Use `auto` tracks for fit-to-content, `fr` tracks for proportional fill, and fixed/relative tracks when the document needs a stable grid.

## Card Helpers In Grids: Width And Internal Spacing

Two failure modes recur when a card/tile helper built from `block(...)` is placed into grid tracks.

### Auto-Width Blocks Shrink-Wrap

A `block` without an explicit `width` sizes to its content, even inside an equal `1fr` grid track. A row of cards then renders with unequal widths and ragged gutters because each box hugs its own text.

Give card helpers `width: 100%` so each card fills its track:

```typst
#let metric-card(value, label) = block(
  width: 100%, // without this the card shrink-wraps to its text
  height: 1.1in,
  inset: 8pt,
  radius: 4pt,
  fill: white,
)[
  ...
]

#grid(
  columns: (1fr, 1fr, 1fr),
  gutter: 8pt,
  metric-card([671], [Dashboards]),
  ...,
)
```

Content that wraps (long paragraphs) can mask the bug: paragraphs fill the available width, so text-heavy cards look full-width while short-text cards shrink. Fix the helper, not the call sites.

### Paragraph Spacing Dominates Inside Cards

Separate `#text(...)` elements on their own markup lines with `v(...)` between them become separate paragraphs. The visible gap between them is then dominated by `par.spacing` (default `1.2em`, resolved against the surrounding text size — about 19pt in a 16pt document), not by a small explicit `v(0.03in)`. Tiny intended gaps silently become huge ones.

Take control of paragraph spacing inside the helper:

```typst
#let metric-card(value, label) = block(width: 100%, height: 1.1in, inset: 8pt)[
  #set par(spacing: 0pt) // gaps now come only from explicit v(...)
  #align(center + horizon)[
    #text(size: 25pt, weight: "bold", value)
    #v(0.08in)
    #text(size: 13pt, label)
  ]
]
```

Rules of thumb:

- In a fixed-height card, top-aligned content piles all leftover space at the bottom. Use `align(center + horizon)` for stat tiles.
- For title-plus-body cards, set a moderate `par(spacing: 0.5em)` in the helper so the title–body gap stays proportionate.
- When one card body legitimately holds several paragraphs that should spread out in a tall fixed-height card, scope larger spacing to that body (`#set par(spacing: 1.1em)` at the start of the content block) instead of reverting the helper default.
- A helper change restyles every call site. Render each page that uses the helper to PNG and inspect before reporting done.

## Measuring And Reactive Layout

`measure` needs context when used in document flow because final sizes depend on styles and placement:

```typst
#context {
  let w = measure([Sample]).width
  [Width: #w]
}
```

Use measurement sparingly. Many layouts can be expressed directly with `auto`, `fr`, `align`, `grid`, and `stack` without measuring.

Use `layout` when a custom element needs access to the available region:

```typst
#layout(size => [
  Available width: #size.width
])
```

## Common Layout Fixes

- Same line left/right content: `Left #h(1fr) Right`
- Center a block of fixed width: `#align(center, block(width: 60%)[...])`
- Keep content inline: wrap it in `box(...)`.
- Force content out of a paragraph: wrap it in `block[...]`.
- Avoid a heading stranded at page bottom: headings are sticky by default; custom heading show rules should usually return a block.
- Make a table column fill remaining width: use `1fr`.
- Make a label fit its text: use `auto`.
- Make a figure scale to text width: use `image(..., width: 100%)` inside the figure.
- Cards in equal grid tracks render with unequal widths: add `width: 100%` to the card `block`.
- A gap inside a card is far larger than its explicit `v(...)`: set `par(spacing: ...)` inside the card helper.
