# Serialization and SVG

Primary files:

- `src/shapes/Object/Object.ts`
- `src/shapes/Object/FabricObjectSVGExportMixin.ts`
- `src/parser/parseAttributes.ts`
- `src/parser/constants.ts`
- `src/parser/normalizeValue.ts`
- `src/util/misc/objectEnlive.ts`

## `toObject`

- `FabricObject#toObject(propertiesToInclude = [])` serializes common object state and custom properties.
- Custom properties come from:
  - `FabricObject.customProperties`
  - the concrete constructor's `customProperties`
  - explicit `propertiesToInclude`
- Numeric values are rounded with `config.NUM_FRACTION_DIGITS`.
- Serializable fillers (`Gradient`, `Pattern`) are converted through their own `toObject`.
- `clipPath` is serialized unless `clipPath.excludeFromExport` is true, and adds `inverted` and `absolutePositioned`.
- `includeDefaultValues = false` removes values that match class defaults, but keeps `left`, `top`, and `type`.

## `fromObject` and Enlivening

- Object enlivening depends on `classRegistry`; import/registration order is observable.
- Nested values with known `type` entries may be enlivened through registered classes.
- Fill/stroke gradients and patterns need their classes available for deserialization.
- Abortable async flows are common for SVG/object loading; preserve signal handling when editing parsing code.

## SVG Attribute Normalization

- SVG attribute names map to Fabric property names in `parser/constants.ts`.
- Important mappings:
  - `x` -> `left`
  - `y` -> `top`
  - `cx` -> `left`
  - `cy` -> `top`
  - `r` -> `radius`
  - `vector-effect` -> `strokeUniform`
  - `paint-order` -> `paintFirst`
  - `display` and `visibility` -> `visible`
- `normalizeValue` converts:
  - `vector-effect="non-scaling-stroke"` to `true`; other values to `false`.
  - `fill="none"` and `stroke="none"` to empty string.
  - `stroke-dasharray="none"` to `null`; otherwise to number arrays.
  - nested transforms by multiplying parent and child matrices.
  - parent opacity and visibility into child attributes.
  - `paint-order` to either `'fill'` or `'stroke'`.

## SVG Export

- Shape `_toSVG()` methods emit local geometry and `COMMON_PARTS`.
- `FabricObjectSVGExportMixin` wraps shape fragments with group transforms, common styles, ids, clip paths, and paint-order behavior.
- Object-local SVG geometry is usually centered around `(0, 0)`; the wrapper transform carries scene placement.
- `strokeUniform` is represented through SVG vector-effect behavior during export.

## Common Pitfalls

- Do not compare raw SVG strings loosely; existing tests often assert exact strings.
- Do not parse SVG with ad hoc string rules when parser helpers already handle units, inherited attributes, transforms, and styles.
- If adding an SVG attribute, update attribute maps, parser normalization if needed, class `ATTRIBUTE_NAMES`, and parser/export tests.
- If adding a serialized object property, update types, defaults, `toObject`, `fromObject` expectations, and default-stripping tests.
