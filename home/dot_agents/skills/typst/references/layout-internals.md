# Typst Layout Internals

This reference summarizes the current layout architecture in `typst/typst`.

## Entry Points

- `crates/typst-layout/src/lib.rs` exports `layout_document`, `layout_frame`, and `layout_fragment`.
- `crates/typst-layout/src/pages/mod.rs` lays out root content into `PagedDocument`. It realizes root content, splits it into page runs, lays runs out in parallel, then finalizes pages.
- `crates/typst-layout/src/flow/mod.rs` lays content into one `Frame` or many `Fragment` frames. It realizes content into block or inline children, then calls `layout_flow`.
- `crates/typst-layout/src/rules.rs` registers paged native show rules. This is the bridge from user elements to layoutable structures.

## Library vs Layout

Public element definitions live in `crates/typst-library/src/...`.

- Layout functions and types: `crates/typst-library/src/layout/`
- Paragraph/model elements: `crates/typst-library/src/model/`
- Text elements: `crates/typst-library/src/text/`

Actual paged layout lives in `crates/typst-layout/src/...`.

- Flow/page breaking: `flow/`
- Inline and paragraph layout: `inline/`
- Block and box sizing: `flow/block.rs`, `inline/box.rs`
- Grid/table layout: `grid/`
- Math layout: `math/`
- Shapes/images/transforms/padding/stacks: top-level modules in `typst-layout`

When changing behavior, inspect both sides: public fields/defaults/casts in `typst-library`, and the layouter plus show rule in `typst-layout`.

## Core Data Types

- `Region` (`crates/typst-library/src/layout/regions.rs`): a single available rectangle with `size: Size` and `expand: Axes<bool>`.
- `Regions`: a sequence of same-width regions. It stores the remaining first-region height, full/base height for relative sizing, finite backlog heights, and an optional repeated last height.
- `Frame` (`layout/frame.rs`): final positioned output with `size`, optional `baseline`, positioned `FrameItem`s, and `FrameKind::{Soft,Hard}`.
- `Fragment`: a sequence of frames returned by breakable layout.
- `Sizing` (`layout/container.rs`): `Auto`, `Rel(Rel)`, or `Fr(Fr)`.
- `Alignment` (`layout/align.rs`): user-visible alignment that resolves through `TextElem::dir` into fixed global `Start/Center/End`.

## Realization And Flow

`layout_fragment` in `flow/mod.rs`:

1. Checks that expansion into infinite axes is rejected.
2. Realizes `Content` with `RealizationKind::LayoutFragment`.
3. Determines `FlowMode::{Root,Block,Inline}`.
4. Calls `layout_flow`.

`layout_flow`:

1. Builds shared configuration: columns, footnotes, line numbers, text direction.
2. Calls `flow/collect.rs` to turn realized elements into `Child` values.
3. Repeatedly calls `flow/compose.rs::compose` for each region until work is done.

`flow/collect.rs` recognizes paragraphs, vertical spacing, blocks, placement, flushes, breaks, and tags. It eagerly lays out paragraph lines because line layout depends on the base width, not the eventual page break.

`flow/compose.rs` handles page/column insertions, floats, footnotes, columns, and restarts layout when insertions shrink available space.

`flow/distribute.rs` consumes `Child`s into one region, deciding what fits, collapsing weak spacing, handling sticky blocks, processing spills, resolving fractional spacing/blocks, and positioning frames.

## Sizing

`Sizing::Auto` means fit content on the relevant axis. `Sizing::Rel` resolves against a base size. `Sizing::Fr` participates in remaining-space distribution only in supported contexts.

For boxes and unbreakable blocks, `flow/block.rs::unbreakable_pod`:

- Treats `Auto` and `Fr` like the available base size while preparing the child region.
- Resolves `Rel` against the base axis.
- Shrinks the child region by inset.
- Sets `expand` true for non-auto finite axes so the child is forced to that size.

For breakable blocks, `flow/block.rs::breakable_pod`:

- Inherits outer `Regions` for auto/fractional height.
- For fixed relative height, distributes the fixed height over the current and following regions and disables repeated `last`.
- Resolves width against the base width.
- Shrinks each region component by inset.

`pad.rs` contains the inverse relationship for padding:

- `shrink(size, inset)` subtracts resolved insets from the available region.
- `grow(frame, inset)` expands a frame so that shrinking the grown size by the relative inset recovers the child size, then translates contents inward.

Inset relativeness is intentionally not the same as width/height relativeness. For containers, relative widths/heights are relative to the parent/base size, while relative insets/outsets are relative to the box/block size excluding outset.

## Boxes And Blocks

Public definitions:

- `BoxElem`: `crates/typst-library/src/layout/container.rs`
- `BlockElem`: same file

Implementation:

- Inline boxes: `crates/typst-layout/src/inline/box.rs`
- Blocks: `crates/typst-layout/src/flow/block.rs`

Boxes are inline-level containers. Blocks are block-level containers and paragraph boundaries. Both lay out a body into a "pod" region, enforce expansion, apply inset with `pad::grow`, then apply clipping, fill, stroke, radius, outset, and labels.

Important differences:

- `BoxElem` can have fractional width in paragraphs. Its height is `Smart<Rel<Length>>`, not general `Sizing`.
- `BlockElem` can be breakable and can have fractional height.
- Explicit boxes/blocks form hard frame boundaries for gradient relativeness.
- Box baseline shift is applied after final sizing and inset so relative baseline shifts resolve against final height.

## Alignment

Public alignment is in `crates/typst-library/src/layout/align.rs`.

- Horizontal `start`/`end` are direction-aware; `left`/`right` are physical.
- Vertical alignment is independent of text direction.
- `Alignment::fix` resolves missing axes to defaults and returns `Axes<FixedAlignment>`.
- `FixedAlignment::position(extent)` returns `0`, `extent / 2`, or `extent`.

Flow alignment happens late in `flow/distribute.rs::finalize`:

- Used size is computed from frames, spacing, and insertions.
- If the region expands, output size is the region size; otherwise it shrinks to used size, capped by region size.
- Horizontal frame position is `align.x.position(size.x - frame.width())`.
- Vertical free space is controlled by a `ruler` that tracks the strongest vertical alignment encountered; frame y is `offset + ruler.position(free)`.
- Absolutely placed elements use explicit `align_y` if provided; otherwise they track current flow offset.

Stacks have independent main-axis handling in `stack.rs`: stack direction chooses the main axis, fractional spacing fills remaining main-axis space, and `AlignElem` affects both main and cross axes.

## Inline And Paragraph Layout

Public paragraph definition: `crates/typst-library/src/model/par.rs`.

Implementation: `crates/typst-layout/src/inline/`.

Pipeline in `inline/mod.rs`:

1. Realize paragraph content with `RealizationKind::LayoutPar`.
2. Build inline `Config` from paragraph fields, text style, direction, hyphenation, and alignment.
3. `inline/collect.rs` collects text, spaces, inline boxes, equations, and inline items.
4. `inline/prepare.rs` performs BiDi and preparation.
5. `inline/linebreak.rs` chooses line breaks.
6. `inline/finalize.rs` determines output width and calls `inline/line.rs::commit` for frames.

Paragraph collection in flow inserts weak paragraph spacing before and after lines. Leading is inserted between line frames. Widow/orphan costs affect the `need` stored on edge lines, and `flow/distribute.rs` uses that need to decide whether to break before a line.

Paragraph width in `inline/finalize.rs`:

- If width is infinite, or if not expanding and no line has fractional spacing, the paragraph frame fits the max line width plus hanging indent.
- Otherwise it expands to the region width.

First-line indent only applies in semantic paragraphs and only when the paragraph's horizontal alignment is the text direction start.

## Spacing, Breaks, And Fractions

Flow spacing is represented as relative or fractional children with weakness levels.

- Weak relative spacing collapses with adjacent weak spacing; the stronger/larger applicable spacing wins.
- Fractional spacing trims trailing weak spacing and fills remaining finite vertical space.
- Forced/weak breaks are handled in `flow/distribute.rs::break_`.
- Sticky blocks can migrate with following content unless doing so cannot improve the region.
- Fractionally sized block heights are laid out after remaining space is known.

Stack spacing is handled separately in `stack.rs` and respects the stack direction axis.

## Placement, Floats, Footnotes, Columns

`PlaceElem` collection builds `PlacedChild` with resolved horizontal alignment, optional vertical alignment, placement scope, float flag, clearance, and delta.

- Non-floating `place` stays out of normal sizing but is positioned in the output frame.
- Floating `place` is processed by `Composer::float`; if it fits, it becomes an insertion and triggers relayout because available space shrinks.
- Automatic vertical float placement chooses top or bottom based on where the float's midpoint would land.
- Parent-scoped placement is currently available only for floating placement.

Columns are configured in `flow/mod.rs::configuration`, then `compose.rs` converts page regions into per-column same-width regions and stitches column frames back together according to text direction.

Footnotes are root-flow only. They can trigger relayout or migration to preserve the invariant that entries appear on the same page as references when possible.

## Common Failure Modes

- Resolving relative sizes against the wrong base (`regions.size` vs `regions.base` vs frame size).
- Forgetting that insets shrink before child layout and grow after child layout.
- Applying alignment before final used/free space is known.
- Treating semantic paragraphs and inline layout as equivalent.
- Ignoring direction-aware `start`/`end`.
- Introducing infinite expansion.
- Breaking weak spacing collapse around blocks, floats, or page/column breaks.
- Forgetting that a `Frame` baseline defaults to its bottom when unset.
