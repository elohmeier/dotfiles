# Geometry and Coordinates

Primary files:

- `src/shapes/Object/ObjectGeometry.ts`
- `src/shapes/Object/InteractiveObject.ts`
- `src/util/misc/resolveOrigin.ts`
- `src/util/misc/matrix.ts`
- `src/shapes/Object/ObjectGeometry.spec.ts`

## Coordinate Planes

- Scene/canvas plane: object coordinates after object and group transforms, before viewport zoom/pan.
- Parent plane: the group's plane, or the canvas plane for ungrouped objects.
- Viewport/screen plane: scene coordinates transformed by `canvas.viewportTransform`.
- `aCoords` describe corners in scene coordinates and do not change when only zoom/pan changes.

## Origins and Position

- Current default origin is `center`/`center`.
- `left` and `top` are the position of the object's current origin in the parent plane.
- `resolveOrigin` maps origins relative to center:
  - `left`/`top`: `-0.5`
  - `center`: `0`
  - `right`/`bottom`: `0.5`
  - numeric origins are normalized as `origin - 0.5`
- Use helpers instead of manual math:
  - `getXY` / `setXY` for scene coordinates.
  - `getRelativeXY` / `setRelativeXY` for parent-plane coordinates.
  - `getCenterPoint` / `getRelativeCenterPoint`.
  - `getPositionByOrigin` and `setPositionByOrigin`.
  - `positionByLeftTop` when user intent is top-left placement.

## `setCoords` and Corner Data

- `setCoords()` calculates `aCoords` using `calcACoords()`.
- `calcACoords()` uses relative center, object angle, and `_getTransformedDimensions()`.
- `getCoords()` returns `[tl, tr, br, bl]`; if grouped, it applies the group transform.
- Interactive objects extend `setCoords()` to also update control coordinates.
- Since Fabric 6, rendering controls does not call `setCoords()` for you; update coordinates explicitly after manual geometry changes.

## Bounds and Hit Tests

- `getBoundingRect()` creates an axis-aligned bounding box from `getCoords()`.
- `intersectsWithRect`, `intersectsWithObject`, `isContainedWithinRect`, and `containsPoint` operate on polygon corners/bounding boxes, not on an arbitrary rendered pixel mask.
- `isOnScreen()` checks canvas `vptCoords`, corner presence, rectangle intersection, and viewport containment for very large objects.

## Transform Matrices

- `calcOwnMatrix()` composes translate-to-center, scale, skew, angle, and flips.
- `calcTransformMatrix()` multiplies the parent group transform unless `skipGroup` is true.
- Matrix caches are keyed by geometry, transform, stroke width, flips, and origin values. If a new property affects transforms, update the key logic.

## Dimensions, Stroke, and Scaling

- `_getNonTransformedDimensions()` returns `width`/`height` plus `strokeWidth`.
- `_getTransformedDimensions()` calculates the object-aligned transformed bounding dimensions.
- With `strokeUniform: false`, stroke is included before scaling, so scale multiplies stroke.
- With `strokeUniform: true`, stroke is added after scaling, so scale does not multiply stroke.
- `getScaledWidth()` and `getScaledHeight()` do not include group transform according to the current TODO in code.
- `scaleToWidth` and `scaleToHeight` use the current bounding rect factor so rotated objects fit the requested axis-aligned size.
