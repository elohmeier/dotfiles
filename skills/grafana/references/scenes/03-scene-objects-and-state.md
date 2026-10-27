# Scene objects and state — core concepts

Everything in `@grafana/scenes` is a scene object. Layouts, panels, variables, query runners, the `SceneApp` itself — all extend `SceneObjectBase`. Understanding the state, lifecycle, and graph is essential.

## Scene object = state + class + renderer

A scene object has three parts:

```tsx
import {
  SceneComponentProps,
  SceneObjectBase,
  SceneObjectState,
} from "@grafana/scenes";
import React from "react";

// 1. State interface
interface CounterState extends SceneObjectState {
  count: number;
}

// 2. Class
export class Counter extends SceneObjectBase<CounterState> {
  public static Component = CounterRenderer;

  public constructor(state?: Partial<CounterState>) {
    super({ count: 0, ...state });
  }

  public onIncrement = () => {
    this.setState({ count: this.state.count + 1 });
  };
}

// 3. Renderer
function CounterRenderer({ model }: SceneComponentProps<Counter>) {
  const { count } = model.useState();
  return (
    <div>
      <span>Count: {count}</span>
      <button onClick={model.onIncrement}>+</button>
    </div>
  );
}
```

Three rules to internalize:

1. **State is immutable.** `Object.freeze`-d at construction; `setState({ ... })` creates a new state object.
2. **Components subscribe via `model.useState()`.** Reading `model.state.x` directly is fine for one-off reads but won't trigger re-renders on change.
3. **Methods belong on the class, not in the renderer.** Keep the renderer pure — call `model.onSomething(...)` from event handlers.

## State requirements

Every state interface must extend `SceneObjectState`:

```ts
interface SceneObjectState {
  key?: string; // Auto-generated UUID
  $timeRange?: SceneTimeRangeLike; // Time range provider
  $data?: SceneDataProvider; // Data provider
  $variables?: SceneVariables; // Variable set
  $behaviors?: Array<SceneObject | SceneStatelessBehavior>; // Behaviors
}
```

The `$`-prefixed slots are special: they propagate down the scene graph. A `VizPanel` deep in the tree will find the closest ancestor with `$data` and use it.

## The scene graph

When you put scene object `A` into the state of scene object `B` (e.g., `new Parent({ body: child })`), `child.parent === parent` is set automatically — but **only when `parent` is activated** (mounted).

A scene object has exactly one parent. **Never put the same instance in two places.** Either `clone()` it, or wrap with `SceneObjectRef`:

```ts
// BAD — shared between two parents
const shared = new SomePanel({...});
new SceneFlexLayout({ children: [shared, shared] });  // Second usage corrupts parent ref

// GOOD — clone
new SceneFlexLayout({ children: [shared, shared.clone()] });

// GOOD — Ref (reference, not ownership)
import { SceneObjectRef } from '@grafana/scenes';
const ref = shared.getRef();
class Holder extends SceneObjectBase<{ panelRef: SceneObjectRef<SomePanel> }> { ... }
```

## Walking the graph: `sceneGraph`

`sceneGraph` is a utility object exported from `@grafana/scenes` for traversing the tree:

```ts
import { sceneGraph } from "@grafana/scenes";

sceneGraph.getVariables(this); // closest $variables up the tree
sceneGraph.getData(this); // closest $data
sceneGraph.getTimeRange(this); // closest $timeRange
sceneGraph.findByKey(root, "some-uuid"); // find by state.key
sceneGraph.findObject(root, predicate); // first match
sceneGraph.findAllObjects(root, predicate);
sceneGraph.getAncestor(this, predicate); // walk upward
sceneGraph.interpolate(this, "${var:csv}"); // run variable interpolation in this object's scope
```

Use `sceneGraph.getData(this)` from inside a custom object's renderer or activation handler when you need to read the data the panel above is providing.

## Activation lifecycle

A scene object is **activated** when its renderer is mounted in the DOM, **deactivated** when unmounted. Activation runs in tree order (root first).

Register activation handlers via `addActivationHandler` in the constructor:

```ts
export class MyObject extends SceneObjectBase<MyState> {
  constructor(state: MyState) {
    super(state);
    this.addActivationHandler(this._onActivate);
  }

  private _onActivate = () => {
    // Subscribe, fetch, kick off side effects
    const sub = sceneGraph.getTimeRange(this).subscribeToState((newRange) => {
      // react
    });

    // Return a deactivation handler
    return () => sub.unsubscribe();
  };
}
```

The deactivation handler runs in the reverse order. Always return cleanup if you subscribed to anything.

## Subscribing to other objects

Inside a class method or handler, you can subscribe to any other scene object's state changes:

```ts
const subscription = otherObject.subscribeToState((newState, oldState) => {
  if (newState.value !== oldState.value) {
    this.setState({ derived: compute(newState.value) });
  }
});
```

Always store the unsubscribe to call from the deactivation handler. RxJS `Unsubscribable` is the contract.

## Reactive UI — `model.useState()`

Inside a renderer, `model.useState()` is what makes React re-render when state changes:

```tsx
function MyRenderer({ model }: SceneComponentProps<MyObject>) {
  // Re-renders when ANY state field changes
  const { foo, bar } = model.useState();

  // Or read once without subscribing — won't update on changes
  const baz = model.state.baz;

  return <>{foo}</>;
}
```

`useState()` is a hook — same rules as React hooks (don't call conditionally, etc.).

## EmbeddedScene — the canonical container

`EmbeddedScene` is just a scene object whose state holds `body` (main content) plus `controls` (optional top row):

```ts
new EmbeddedScene({
  $timeRange: new SceneTimeRange({ from: 'now-6h', to: 'now' }),
  $variables: new SceneVariableSet({ variables: [...] }),
  $data: new SceneQueryRunner({ ... }),
  body: new SceneFlexLayout({ children: [...] }),
  controls: [
    new VariableValueSelectors({}),
    new SceneControlsSpacer(),
    new SceneTimePicker({ isOnCanvas: true }),
    new SceneRefreshPicker({ intervals: ['5s', '1m', '1h'], isOnCanvas: true }),
  ],
});
```

Whatever you put in `$data`, `$timeRange`, `$variables` is available to every descendant via the scene graph lookup.

## Cloning

```ts
const cloned = sceneObj.clone(); // Deep clone with same state
const modified = sceneObj.clone({ title: "New" }); // Override fields

// Just the state, no new object:
import { sceneUtils } from "@grafana/scenes";
const stateCopy = sceneUtils.cloneSceneObjectState(state);
```

Cloning is the right tool when you need the same logical content (a panel, a layout) used in multiple places.

## URL sync for custom objects

To make your custom object participate in URL sync, attach a `SceneObjectUrlSyncConfig`:

```ts
import { SceneObjectUrlSyncConfig } from "@grafana/scenes";

export class FilterInput extends SceneObjectBase<{ value: string }> {
  protected _urlSync = new SceneObjectUrlSyncConfig(this, {
    keys: () => ["filter"],
    getUrlState: () => ({ filter: this.state.value }),
    updateFromUrl: (values) => {
      if (values.filter && values.filter !== this.state.value) {
        this.setState({ value: values.filter });
      }
    },
  });
}
```

Now the value appears in URL as `?filter=<value>` and the back/forward buttons restore it.

## Patterns to use sparingly

- **Don't cache scene graph lookups in fields.** They become stale across activation cycles. Look them up at use time inside the activation handler.
- **Don't mutate state.** Even `state.list.push(...)` will not trigger re-renders. Always `setState({ list: [...state.list, item] })`.
- **Don't read state in the constructor of a child object based on a parent.** Parent reference is set later — defer to the activation handler.
