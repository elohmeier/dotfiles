# Rectangle Behavior

Primary files:

- `src/shapes/Rect.ts`
- `src/shapes/Rect.spec.ts`
- `src/shapes/Object/Object.ts`
- `src/parser/constants.ts`
- `src/parser/normalizeValue.ts`

## Rect Defaults and Properties

- `Rect` extends `FabricObject`.
- `Rect.type` is `'Rect'`.
- `Rect.ownDefaults` contains only `rx: 0` and `ry: 0`; inherited defaults supply position, fill, stroke, origin, caching, and transforms.
- `Rect.cacheProperties` extends base cache properties with `rx` and `ry`, because rounded corners change cached rendering.
- `Rect.toObject()` always requests `rx` and `ry` in addition to caller-specified properties.

## `rx` / `ry` Initialization

- After options are applied, `_initRxRy()` mirrors a single provided radius:
  - if `rx` is truthy and `ry` is falsy, `ry = rx`
  - if `ry` is truthy and `rx` is falsy, `rx = ry`
- Zero is treated as "missing" for this mirroring logic because the check is truthy/falsy.
- Later property changes do not automatically mirror `rx` and `ry`; the mirroring is constructor-time behavior.

## Rendering Model

- Rect rendering is object-local and centered:
  - local `x = -width / 2`
  - local `y = -height / 2`
  - path width/height are `width` and `height`
- `rx` is clamped to at most `width / 2`; `ry` is clamped to at most `height / 2`.
- Rounded corners use cubic Beziers with `kRect`.
- The path is closed, then `_renderPaintInOrder(ctx)` decides fill/stroke order.
- A rect with no width and no height is not rendered unless stroke rules make it visible; `isNotVisible()` also checks opacity and `visible`.

## SVG Parsing

- `Rect.ATTRIBUTE_NAMES` includes shared attributes plus `x`, `y`, `rx`, `ry`, `width`, and `height`.
- SVG `x` maps to Fabric `left`; SVG `y` maps to Fabric `top`.
- `Rect.fromElement()` defaults missing `left`, `top`, `width`, `height`, and `visible`; it sets `visible` to false when width or height is zero.
- SVG `vector-effect="non-scaling-stroke"` normalizes to `strokeUniform: true`.
- `stroke-dasharray`, `paint-order`, visibility, opacity, and transform attributes are normalized in parser utilities, not in `Rect` itself.

## SVG Export

- `Rect._toSVG()` emits a `<rect>` nested in the object-level wrapper from common SVG export.
- Exported rect coordinates remain object-local:
  - `x="-width / 2"`
  - `y="-height / 2"`
  - `width`, `height`, `rx`, and `ry` are emitted as attributes.
- The outer `<g transform="matrix(...)">` positions the rect in scene space.
- `paintFirst: 'stroke'` becomes `paint-order="stroke"` in SVG output.
- Alpha colors are split into RGB color plus opacity attributes by shared SVG style export.

## Rectangle Tests to Check

- Constructor/type/inheritance.
- `cacheProperties` contains `rx` and `ry`.
- `toObject` and `fromObject`, including fillers such as `Gradient` and `Pattern`.
- `fromElement` with custom SVG attributes and `vector-effect`.
- clone with rounded corners.
- `toSVG` for rounded corners, alpha fill/stroke, id, and paint order.
- `includeDefaultValues = false`.
