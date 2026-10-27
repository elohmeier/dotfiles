# Interactions, Selections, Controls, and Borders

Primary files:

- `src/canvas/SelectableCanvas.ts`
- `src/canvas/Canvas.ts`
- `src/canvas/CanvasOptions.ts`
- `src/shapes/ActiveSelection.ts`
- `src/shapes/Object/InteractiveObject.ts`
- `src/shapes/Object/types/BorderProps.ts`
- `src/controls/Control.ts`
- `src/controls/commonControls.ts`
- `src/controls/scale.ts`
- `src/controls/scaleSkew.ts`
- `src/controls/wrapWithFixedAnchor.ts`
- `src/controls/wrapWithFireEvent.ts`

## Selection Model

- `Canvas`/`SelectableCanvas` owns `_activeObject`; `getActiveObjects()` returns the objects inside an `ActiveSelection`, the single active object, or an empty array.
- `setActiveObject()` and `discardActiveObject()` are public event-firing wrappers around `_setActiveObject()` and `_discardActiveObject()`.
- `_setActiveObject()` calls `onSelect`, assigns `_activeObject`, sets canvas on an `ActiveSelection`, and calls `object.setCoords()`.
- `_discardActiveObject()` calls `onDeselect`; returning `true` from `onDeselect` cancels deselection.
- `_fireSelectionEvents()` compares previous and current active objects and fires `selected`, `deselected`, `selection:created`, `selection:updated`, or `selection:cleared`; it also invalidates `_objectsToRender`.

## ActiveSelection

- `ActiveSelection` extends `Group`, but it is a temporary selection wrapper, not a normal persisted group.
- It uses `ActiveSelectionLayoutManager`; replacing it can break interactive group selections.
- `multiSelectionStacking` controls insertion order:
  - `canvas-stacking` respects canvas stack order.
  - `selection-order` keeps the order objects were selected.
- `canEnterGroup()` blocks selecting ancestor/descendant combinations to avoid circular object trees.
- `enterGroup()` and `exitGroup()` preserve parent/group relationships so selected objects can render in the active selection while returning to their original parent.
- `ActiveSelection.shouldCache()` and `isOnACache()` return false.
- `_renderControls()` draws child borders with `hasControls: false` and `forActiveSelection: true`, then draws the selection controls.

## Target Finding

- `findTarget()` caches event target data during an event and returns duplicated "current" and selection-aware target information.
- Active object controls are checked with viewport coordinates through `activeObject.findControl(getViewportPoint(e), isTouchEvent(e))`.
- Object body hit testing uses scene coordinates.
- `_pointIsInObjectSelectionArea()` checks `getCoords()` plus `padding / zoom`; padding is not stored as separate coordinates.
- `_checkTarget()` requires `visible` and `evented`, then optionally performs per-pixel target finding.
- `selectable: false` prevents selection, but `evented: false` makes events pass through the object.
- `skipTargetFind` disables click target detection, but area selection is controlled separately by `selection`.

## Drag Selection Rectangle

- `_groupSelector` stores `x`, `y`, `deltaX`, and `deltaY` in scene coordinates.
- `_drawSelection()` transforms start/end through `viewportTransform` and draws on the upper/top canvas.
- Canvas selection rectangle styling is controlled by `selectionColor`, `selectionBorderColor`, `selectionDashArray`, and `selectionLineWidth`.
- The selection rectangle border uses `selectionLineWidth`; this is unrelated to object `strokeWidth` and object `borderScaleFactor`.
- `selectionFullyContained` changes whether objects must be fully contained by the drag rectangle.

## Controls and Control Hit Areas

- Interactive objects create per-instance controls with `createObjectDefaultControls()` unless a class overrides `createControls()`.
- `oCoords` are viewport coordinates for control centers and corner/touch hit polygons.
- `setCoords()` on `InteractiveFabricObject` updates both `aCoords` and `oCoords` when a canvas is present.
- `findControl()` only activates controls for the canvas active object.
- `Control.shouldActivate()` requires active object identity, control visibility, and point-in-control-polygon.
- `cornerSize` controls rendered control size; `touchCornerSize` controls larger touch hit areas.
- `Control.sizeX/sizeY` and `touchSizeX/touchSizeY` override object sizes per control.
- `_controlsVisibility` on an object overrides a control's generic `visible` property.
- `Control.positionHandler()` places controls relative to the object bounding box: `x/y = -0.5, 0, 0.5` plus pixel offsets.
- Offset controls such as `mtr` can set `withConnection` so Fabric draws a line from the border to the control.

## Borders vs Object Stroke

- Object `strokeWidth` is part of the rendered object and can affect object dimensions/cache/SVG.
- Interactive border drawing is separate:
  - `hasBorders` toggles the active-object bounding border.
  - `borderColor` and `borderDashArray` style it.
  - `borderScaleFactor` sets control-border line width and is added into border size calculations.
  - `borderOpacityWhenMoving` reduces border opacity while moving.
- `drawBorders()` computes a control-box size from transformed dimensions, padding, stroke, and `borderScaleFactor`.
- For grouped objects or active-selection children, `drawBorders()` uses decomposed transform data and explicitly accounts for stroke.
- `drawControls()` resets the context to retina scaling before rendering controls, so controls are screen-sized rather than object-scaled.
- `transparentCorners` changes whether square/circle controls are stroked or filled; "transparent" square controls do not literally clear pixels on the top canvas.

## Scaling and Transform Actions

- `_setupCurrentTransform()` builds `_currentTransform` with target, action, action handler, corner, origin, pointer offsets, original transform values, and crop data for images.
- Control action names come from `getActionFromCorner()` and `Control.getActionName()`.
- Default controls:
  - corners (`tl`, `tr`, `bl`, `br`) use proportional/free corner scaling through `scalingEqually`.
  - side controls (`ml`, `mr`, `mt`, `mb`) scale or skew depending on `altActionKey`.
  - `mtr` rotates with snapping and has `offsetY: -40`.
- `scaleIsProportional()` combines `canvas.uniformScaling` and `canvas.uniScaleKey`; the key toggles the canvas default.
- `scalingIsForbidden()` honors scaling locks and blocks zero-size objects when scale math would divide by zero.
- `lockScalingFlip` blocks crossing the transform origin during scale actions.
- `wrapWithFixedAnchor()` preserves the anchor point by saving `target.getPositionByOrigin(originX, originY)` and restoring position after the action.
- `wrapWithFireEvent()` fires both canvas `object:<event>` and object `<event>` when an action changes the object.
- `_finalizeCurrentTransform()` clears `_scaling`, calls `target.setCoords()`, and fires `object:modified`/`modified` only if `actionPerformed` is true.

## Width/Height Resize Controls

- `changeWidth`/`changeHeight` modify dimensions rather than scale.
- Dimension changes subtract stroke padding as `strokeWidth / (strokeUniform ? scale : 1)`.
- New dimensions are clamped to at least `1`.
- Textbox controls replace `ml`/`mr` with resize controls while keeping other object controls.
