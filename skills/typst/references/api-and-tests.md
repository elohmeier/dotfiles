# Typst API And Test Map

Use this file to find the public Typst surface and relevant test fixtures.

## Public Layout Surface

`crates/typst-library/src/layout/mod.rs` registers the layout category:

- Units and sizing: `Length`, `Angle`, `Ratio`, `Rel<Length>`, `Fr`, `Abs`, `Em`
- Direction and alignment: `Dir`, `Alignment`
- Page and breaks: `PageElem`, `PagebreakElem`
- Spacing: `VElem`, `HElem`
- Containers: `BoxElem`, `BlockElem`
- Layout tools: `StackElem`, `GridElem`, `ColumnsElem`, `ColbreakElem`, `PlaceElem`, `AlignElem`, `PadElem`, `RepeatElem`, `HideElem`
- Transforms: `MoveElem`, `ScaleElem`, `RotateElem`, `SkewElem`
- Introspection helpers: `measure`, `layout`

Element definitions are usually one file per public function:

- `layout/container.rs`: `box`, `block`, `Sizing`
- `layout/align.rs`: `align`, `alignment`
- `layout/spacing.rs`: `h`, `v`, `Spacing`
- `layout/stack.rs`: `stack`
- `layout/grid/mod.rs` and `layout/grid/resolve.rs`: `grid`, `table`, tracks, cells
- `layout/page.rs`: page size, margins, headers, footers, numbering
- `layout/place.rs`: absolute and floating placement
- `layout/pad.rs`: padding
- `layout/measure.rs`: `measure`
- `layout/layout.rs`: `layout`

## Model And Text Surface

- `crates/typst-library/src/model/par.rs`: paragraph behavior, leading, spacing, justification, linebreaks, indents.
- `crates/typst-library/src/model/heading.rs`: heading block behavior, stickiness, numbering.
- `crates/typst-library/src/model/list.rs`, `enum.rs`, `terms.rs`: list-like layout and spacing.
- `crates/typst-library/src/model/table.rs`: public table surface; implementation mostly uses grid layout.
- `crates/typst-library/src/text/mod.rs`: text styling including size, direction, language, edges, spacing, hyphenation, fallback.

## Paged Show Rules

`crates/typst-layout/src/rules.rs` is the central dispatch map for paged export. Inspect it when a user-visible element does not have a direct layout function.

Examples:

- Lists and enums become `BlockElem::multi_layouter`.
- Terms become a padded `StackElem`.
- Headings become blocks with spacing/stickiness and generated numbering.
- `align`, `pad`, `columns`, `stack`, `grid`, transforms, shapes, images, equations, and PDF markers each register paged rules here.

## Implementation Map

- Flow: `crates/typst-layout/src/flow/{mod,collect,compose,distribute,block}.rs`
- Inline text: `crates/typst-layout/src/inline/{mod,collect,prepare,linebreak,line,finalize,box,shaping,deco}.rs`
- Pages: `crates/typst-layout/src/pages/{mod,collect,run,finalize}.rs`
- Grid/table: `crates/typst-layout/src/grid/{mod,layouter,lines,repeated,rowspans}.rs`
- Math: `crates/typst-layout/src/math/`
- Shapes: `crates/typst-layout/src/shapes.rs`
- Images: `crates/typst-layout/src/image.rs`
- Padding: `crates/typst-layout/src/pad.rs`
- Stacks: `crates/typst-layout/src/stack.rs`
- Transforms: `crates/typst-layout/src/transforms.rs`

## High-Value Test Areas

Suite inputs:

- `tests/suite/layout/align.typ`
- `tests/suite/layout/container.typ`
- `tests/suite/layout/pad.typ`
- `tests/suite/layout/stack.typ`
- `tests/suite/layout/spacing.typ`
- `tests/suite/layout/columns.typ`
- `tests/suite/layout/grid/*.typ`
- `tests/suite/layout/inline/*.typ`
- `tests/suite/layout/flow/*.typ`
- `tests/suite/model/par.typ`
- `tests/suite/text/*.typ`
- `tests/suite/math/alignment.typ`

Render references often reveal past regressions. Search `tests/ref/render/` by feature and issue number. Useful names include:

- Alignment: `align-center-in-flow.png`, `align-in-stack.png`, `align-right.png`, `align-start-and-end.png`, `issue-1398-line-align.png`, `issue-2213-align-fr.png`
- Boxes/blocks/sizing: `box.png`, `box-fr-width.png`, `block-box-fill.png`, `baseline-box.png`, `layout-in-fixed-size-block.png`, `issue-2128-block-width-box.png`
- Paragraphs: `par-basic.png`, `par-leading-and-spacing.png`, `par-spacing-and-first-line-indent.png`, `par-semantic.png`, `par-hanging-indent.png`
- Flow: `flow-fr.png`, `issue-flow-weak-spacing.png`, `issue-flow-overlarge-frames.png`, `flow-widow-forced.png`
- Inline text: `linebreak-overflow.png`, `linebreak-overflow-double.png`, `show-text-line-wrapping.png`, `text-spacing.png`, `text-edge.png`
- Grid/table: `grid-align.png`, `grid-cell-align-override.png`, `table-cell-align-override.png`, `table-align-array.png`
- Math alignment: `math-align-basic.png`, `math-align-spacing.png`, `math-equation-align-numbered.png`, `math-mat-align.png`

## Debugging Tips

- `Frame::mark_box` and `Frame::mark_box_in_place` in `layout/frame.rs` can make frame bounds and baselines visible during local investigation.
- Search for `#[typst_macros::time]` names to find profiling spans.
- Search `tests/ref/render/issue-<number>` before modifying behavior around a known regression.
- Use `rg "with_body|single_layouter|multi_layouter|InlineElem::layouter|BlockElem::"` to find how public elements become layout callbacks.
- Use `rg "resolve\\(styles\\)|get\\(styles\\)|get_ref\\(styles\\)"` in the relevant element implementation to understand style resolution timing.
