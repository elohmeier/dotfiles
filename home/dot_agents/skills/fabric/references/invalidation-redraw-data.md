# Invalidation, Redraw, and Object Data

Primary files:

- `src/shapes/Object/Object.ts`
- `src/shapes/Object/defaultValues.ts`
- `src/shapes/Object/ObjectSerialization.spec.ts`
- `src/shapes/Object/Object.spec.ts`
- `src/shapes/Object/InteractiveObject.ts`
- `src/canvas/StaticCanvas.ts`
- `src/canvas/SelectableCanvas.ts`
- `src/canvas/Canvas.ts`
- `src/canvas/StaticCanvasOptions.ts`

## Dirty State vs Redraw Scheduling

- `dirty` means an object's cache needs repainting.
- `canvas.requestRenderAll()` schedules a canvas render on the next animation frame.
- Setting an object dirty does not by itself schedule a canvas redraw.
- Scheduling a canvas redraw does not by itself make object caches dirty.
- `renderAll()` renders immediately and cancels a pending requested render.
- `requestRenderAll()` is coalesced by `nextRenderHandle`; repeated calls before the next frame schedule only one render.

## Cache Invalidation

- Base `cacheProperties` are listed in `src/shapes/Object/defaultValues.ts`.
- `FabricObject#_set()` marks `dirty = true` when a changed key is in the constructor's `cacheProperties`.
- If a dirty child belongs to a parent, `_set()` bubbles dirty state to the parent; setting dirty false does not clean the parent.
- `stateProperties` can also dirty the parent when changed.
- Shape-specific rendered properties must be added to the class's `cacheProperties`.
- Path/poly controls sometimes call `set('dirty', true)` directly when editing points changes pixels without changing standard cache properties.
- `isCacheDirty()` has side effects: it may resize/clear the cache canvas. Do not call it as a harmless predicate.

## Object Caching

- `objectCaching` enables object caches, but `shouldCache()` also considers parent cache state and `needsItsOwnCache()`.
- Objects in cached groups generally do not get their own cache unless `needsItsOwnCache()` is true.
- `needsItsOwnCache()` returns true for clip paths and for certain fill/stroke/shadow paint-order combinations.
- `clipPath` forces cache-like behavior even when normal object caching is disabled.
- `ActiveSelection` never caches.
- `InteractiveFabricObject#_updateCacheCanvas()` skips cache resize/update during scale transforms when `noScaleCache` is true and the object is the current scaling target.
- `noScaleCache` is a scaling-performance tradeoff: the cached bitmap can look blocky during scaling and is redrawn after scaling ends.

## Canvas Redraw Flow

- `StaticCanvas.add`, `insertAt`, `remove`, stack-order changes, `clear`, `setDimensions`, and viewport changes request renders when `renderOnAddRemove` or method logic says so.
- `renderOnAddRemove` defaults to true, but many bulk flows disable it and call `requestRenderAll()` after the batch.
- `StaticCanvas#renderCanvas()` clears the lower canvas, fires `before:render`, renders background, applies the viewport transform, renders objects, draws controls/overlays, fires `after:render`, then runs cleanup.
- `SelectableCanvas#renderAll()` also manages the upper/top context for selection boxes, drag effects, and lost-context recovery.
- `contextTopDirty` tracks when the upper canvas needs cleanup.
- `renderTop()` redraws only the top canvas and fires `after:render` for that context.
- `controlsAboveOverlay` controls whether interactive controls render before or after overlay.

## Coordinates and Redraw Are Separate

- `setCoords()` updates `aCoords`/`oCoords`; it does not render.
- `requestRenderAll()` renders later; it does not recompute coordinates unless rendering path or caller does so separately.
- Adding an object to a canvas calls `_onObjectAdded()`, sets its canvas, and calls `setCoords()`.
- Viewport transform changes recalculate canvas viewport boundaries and, on `SelectableCanvas`, refresh active object coords.
- Transform finalization calls `target.setCoords()` and fires modification events if needed.

## Selection Render Invalidation

- `_objectsToRender` caches the object list for rendering when selection stacking rules are in effect.
- Adding/removing objects, stack-order changes, and selection event transitions clear `_objectsToRender`.
- With `preserveObjectStacking: false`, an active object is rendered last by `_chooseObjectsToRender()`.
- When serializing/exporting an object inside an active selection, `SelectableCanvas` temporarily realizes the active-selection group transform on the child and then restores original properties.

## Custom Data on Objects

- Fabric objects accept arbitrary option properties at runtime; tests show `new FabricObject({ name, key2 })` stores them on the instance.
- Arbitrary properties are not serialized by default.
- Include one-off custom data by calling `toObject(['propName'])`.
- Include global custom data by setting `FabricObject.customProperties = ['propName']`.
- Include class-specific custom data by setting `Rect.customProperties = ['propName']` or the relevant subclass's static `customProperties`.
- Cloning uses `toObject()` and `fromObject()`, so custom data is cloned only when it is serialized through custom properties or explicit include lists.
- Prefer namespaced data objects or well-named app keys to avoid colliding with future Fabric properties.
- If a custom property affects rendering, add it to the relevant class's `cacheProperties` and mark dirty when mutating nested values.
- If a custom property affects geometry/selection, update coordinates after mutation and consider adding tests for hit testing and serialization.

## Validation Checklist

- Rendering-only property change: verify cache dirty behavior and a redraw call path.
- Geometry property change: verify `setCoords()` timing and hit/control behavior.
- Transform-control change: verify action events, `object:modified`, fixed anchor, locks, centered transform, flip crossing, and `noScaleCache`.
- Selection change: verify selection events, `_objectsToRender`, active-selection child rendering, and serialization/export from active selections.
- Custom data change: verify `toObject`, clone, load/fromObject, and cache/coords if the data affects appearance or geometry.
