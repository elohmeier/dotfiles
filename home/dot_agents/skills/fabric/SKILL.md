---
name: fabric
description: Use when answering questions, debugging, or changing code for Fabric.js objects, geometry, coordinates, rendering, serialization, SVG parsing/export, controls, or rectangle behavior. Includes Fabric-specific quirks such as center-origin defaults, setCoords, aCoords, strokeUniform, rx/ry handling, classRegistry, defaults, caching, and object/SVG serialization.
---

# Fabric.js Internals

Use this skill when a user or agent needs to understand how Fabric.js behaves rather than how a generic canvas library behaves. Prefer the repository source over memory when details matter.

## First checks

- Start from the relevant class under `src/shapes`, `src/canvas`, `src/parser`, or `src/util`.
- Use `rg` for exact property/method names before assuming behavior.
- Check nearby `*.spec.ts` files; many Fabric quirks are documented as test expectations.
- For behavior changes, add or update focused tests in the same area.

## Reference Map

Load only the references needed for the task:

- `references/object-model.md`: class defaults, `set`, dirty/cache behavior, class registry, serialization defaults.
- `references/geometry-coordinates.md`: `left`/`top`, origins, scene vs viewport coordinates, `setCoords`, transforms, bounding boxes, scaling.
- `references/interactions-selection-controls.md`: active selections, target finding, transform setup, scaling handlers, controls, borders, selection rectangle.
- `references/invalidation-redraw-data.md`: dirty/cache invalidation, render scheduling, top canvas cleanup, custom data attachment and serialization.
- `references/rectangles.md`: `Rect`, `rx`/`ry`, SVG rect parsing/export, rounded-corner rendering, rectangle visibility.
- `references/serialization-svg.md`: `toObject`, `fromObject`, SVG attribute normalization, fillers, custom properties, `includeDefaultValues`.
- `references/text-sizing-layout.md`: `Text`/`IText`/`Textbox`, font measurement, `fontSize`, `lineHeight`, `charSpacing`, wrapping, min width, text padding misconceptions.

## Core Rules

- Fabric object defaults are class-level `ownDefaults` merged through `getDefaults`; do not assume prototype defaults.
- Default object origin is `center`/`center` in current code. Older snippets may assume `left`/`top`.
- `left` and `top` mean "position of the current origin in the parent plane", not always the top-left corner.
- Direct `set`/property changes for geometry do not refresh hit-test/control coordinates; call `setCoords()` when the object must be interactable or queried immediately.
- `aCoords` are scene coordinates and do not include viewport transform. Control coordinates are handled separately by interactive objects.
- Stroke affects dimensions. `strokeUniform` changes whether stroke is included before or after object scaling.
- Control borders and selection rectangles are interaction overlays, not object strokes. `borderScaleFactor`, `cornerSize`, `selectionLineWidth`, and `strokeWidth` live in different systems.
- Scaling from controls is action-handler driven; check `src/controls/scale.ts`, `scaleSkew.ts`, and `wrapWithFixedAnchor.ts` before changing transform behavior.
- Active selections are temporary groups with special layout/rendering semantics; do not treat them as normal persistent groups.
- `dirty` invalidates an object's cache, while `requestRenderAll()` schedules a canvas redraw. They are related but not interchangeable.
- Negative `scaleX`/`scaleY` passed through `_set` become positive scale plus `flipX`/`flipY`; zero scale is constrained to `0.0001`.
- Rendering uses an object-local path centered at `(0, 0)` for most shapes; transforms place it on the canvas.
- SVG import/export does not mirror browser SVG behavior exactly; verify through parser/export tests.
- Registered classes matter for enlivening JSON/SVG. Shapes call `classRegistry.setClass` and SVG-capable shapes also call `setSVGClass`.
- Arbitrary object properties can exist at runtime, but are not serialized/cloned unless included through `toObject([...])` or `customProperties`.
- Text dimensions are measured layout data, not just declared `fontSize`; check text sizing rules before answering fit, wrapping, padding, or autosize questions.

## Editing Guidance

- Keep changes local to the owning class or utility unless tests show shared behavior is wrong.
- When changing a property that affects visual output, update `cacheProperties` if cached rendering must be invalidated.
- When adding serialized properties, include them in `toObject`, defaults, types, and tests for `includeDefaultValues = false` when applicable.
- For geometry fixes, test rotated, scaled, skewed, stroked, grouped, and `strokeUniform` cases as risk demands.
- For SVG fixes, test both `fromElement`/`loadSVGFromString` and `toSVG` when behavior is round-trippable.
- For text layout fixes, test `Text`/`IText`/`Textbox` separately when relevant, including styled characters, multiline text, wrapping, and changed font metrics.
