# Object Model Quirks

Primary files:

- `src/shapes/Object/Object.ts`
- `src/shapes/Object/FabricObject.ts`
- `src/shapes/Object/defaultValues.ts`
- `src/CommonMethods.ts`
- `src/ClassRegistry.ts`

## Defaults and Construction

- `fabricObjectDefaultValues` defines base defaults such as `originX: CENTER`, `originY: CENTER`, `strokeWidth: 1`, `strokeUniform: false`, `objectCaching: true`, `centeredRotation: true`, and `dirty: true`.
- Each class can define `static ownDefaults`; `getDefaults()` merges parent defaults and class defaults.
- Constructors usually call `super()`, assign `ownDefaults`, then apply options with `setOptions`.
- Do not infer defaults from TypeScript declarations; read `ownDefaults` and `getDefaults`.

## `set`, `_set`, and Side Effects

- `CommonMethods#set` sets one property or an object of properties and returns `this`.
- `set` does not refresh borders/controls for position or dimension changes. Call `setCoords()` after geometry changes when hit testing, controls, or bounding data must be current.
- `FabricObject#_set` handles internal side effects:
  - `scaleX`/`scaleY` are constrained by `_constrainScale`.
  - negative scale flips `flipX`/`flipY` and stores a positive scale.
  - plain shadow objects become `Shadow` instances.
  - keys listed in the constructor's `cacheProperties` mark the object `dirty`.
  - keys listed in `stateProperties` can dirty a parent.

## Caching and Dirty State

- Base `cacheProperties` include fill/stroke properties, width, height, paint order, `strokeUniform`, background color, and `clipPath`.
- Shape-specific visual properties must be added to that class's `cacheProperties`; `Rect` adds `rx` and `ry`.
- `objectCaching` is a rendering/cache concern, not a geometry-coordinate refresh mechanism.
- `noScaleCache` is an interactive-object default and affects cache behavior while scaling, not object dimensions.

## Registry and Enlivening

- `classRegistry` maps serialized/SVG type names to classes.
- Shape classes register themselves, usually at file end:
  - `classRegistry.setClass(Rect)`
  - `classRegistry.setSVGClass(Rect)` for SVG element parsing.
- Code-splitting matters: the registry contains only classes whose modules were imported.
- JSON/SVG enlivening fails or falls back incorrectly if the relevant class was never registered.

## Serialization Defaults

- `toObject` starts with common object props, merges custom properties, then removes defaults if `includeDefaultValues` is false.
- `_removeDefaultValues` compares against `getDefaults()` when static defaults exist.
- Always test "without default values" when adding class defaults or serialized shape props.
